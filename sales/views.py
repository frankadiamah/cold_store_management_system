from decimal import Decimal
import json
from io import BytesIO
import base64
from urllib import request
import qrcode
from datetime import datetime, timedelta
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.db import transaction
from django.db.models import Sum, F, ExpressionWrapper, DecimalField

# from sales.utils import visible_queryset_for_user
from users.utils import has_any_group
from .models import Sale, SaleItem, CreditPayment
from .forms import SaleForm, SaleItemForm, CreditPaymentForm
from inventory.models import Product, ProductWeightPrice

from django.http import HttpResponse
from reportlab.lib.pagesizes import A5, landscape
from reportlab.pdfgen import canvas

from inventory.services import consume_weight

# from .services import deduct_weight_from_product
VAT_RATE = Decimal("0.04")  # 4.5%

def user_sale_type(user):
    if user.groups.filter(name="Wholesale").exists():
        return "wholesale"
    if user.groups.filter(name="Retail").exists():
        return "retail"
    return "retail"

# Stock deduction logic (matches client box rule)
def consume_weight_from_product(product, kg_to_sell: Decimal):
    """
    Deduct kg from a weighted product WITHOUT deducting a box until the remaining hits 0.
    Boxes only decrement when cumulative sold reaches exactly box weight.
    """
    if not product.is_weighted:
        raise ValueError("Product is not weighted.")

    bw = Decimal(product.box_weight_kg or 0)
    if bw <= 0:
        raise ValueError("Product box_weight_kg is not set.")

    if product.boxes_in_stock <= 0:
        raise ValueError("No boxes in stock.")

    # initialize remaining
    if Decimal(product.box_remaining_kg or 0) <= 0:
        product.box_remaining_kg = bw

    # check available
    available = product.available_weight_kg()
    if kg_to_sell > available:
        raise ValueError(f"Not enough weight stock. Available: {available}kg")

    kg_left = Decimal(kg_to_sell)

    while kg_left > 0:
        # if current box empty, deduct a box and reset for next
        if Decimal(product.box_remaining_kg) <= 0:
            product.boxes_in_stock -= 1
            if product.boxes_in_stock <= 0:
                product.box_remaining_kg = Decimal("0.00")
                break
            product.box_remaining_kg = bw

        take = min(kg_left, Decimal(product.box_remaining_kg))
        product.box_remaining_kg = Decimal(product.box_remaining_kg) - take
        kg_left -= take

        # if we finished a full box -> NOW deduct 1 box and reset remaining
        if Decimal(product.box_remaining_kg) == 0:
            product.boxes_in_stock -= 1
            if product.boxes_in_stock > 0:
                product.box_remaining_kg = bw
            else:
                product.box_remaining_kg = Decimal("0.00")

    product.save(update_fields=["boxes_in_stock", "box_remaining_kg"])

# Stock deduction logic (matches client box rule)

@login_required
@has_any_group("Admin", "Staff", "Retail", "Wholesale")
@transaction.atomic
def create_sale(request):
    ItemFormset = formset_factory(SaleItemForm, extra=1)
    stype = user_sale_type(request.user)

    # used by your JS to populate weight dropdown & prices
    weights_json = {}
    for wp in ProductWeightPrice.objects.filter(is_active=True).select_related("product"):
        weights_json.setdefault(str(wp.product_id), []).append({
            "id": wp.id,
            "label": f"{wp.weight_kg:g}kg",
            "weight_kg": float(wp.weight_kg),
            "retail_price": float(wp.retail_price),
            "wholesale_price": float(wp.wholesale_price),
        })
# addedd on 26th January 2026
    
    products_json = {}
    for p in Product.objects.all().only("id", "unit_price", "wholesale_price", "is_weighted"):
        products_json[str(p.id)] = {
            "is_weighted": bool(p.is_weighted),
            "retail_price": float(p.unit_price or 0),
            "wholesale_price": float(p.wholesale_price or 0),
        }
# addedd on 26th January 2026
    
    if request.method == "POST":
        sale_form = SaleForm(request.POST)
        formset = ItemFormset(request.POST)

        if sale_form.is_valid() and formset.is_valid():
            sale = sale_form.save(commit=False)
            sale.created_by = request.user
            sale.sale_type = stype
            sale.is_credit = (sale.payment_method == "credit")
            sale.save()

            subtotal = Decimal("0.00")

            # lock products for safe stock update
            # (we will fetch per item using select_for_update)
            for f in formset:
                if not f.cleaned_data or not f.cleaned_data.get("product"):
                    continue

                product = Product.objects.select_for_update().get(id=f.cleaned_data["product"].id)
                qty = int(f.cleaned_data.get("quantity") or 0)
                weight_price = f.cleaned_data.get("weight_price")  # may be None

                item = SaleItem(sale=sale, product=product, quantity=qty)

                # ✅ CASE 1: Weight sale (fish)
                if weight_price:
                    # re-fetch weight_price safely
                    wp = ProductWeightPrice.objects.select_related("product").get(id=weight_price.id)

                    # force correct pricing server-side
                    item.weight_price = wp
                    item.unit_price = wp.wholesale_price if stype == "wholesale" else wp.retail_price

                    sold_kg = Decimal(qty) * Decimal(wp.weight_kg)
                    consume_weight(product=product, kg_to_sell=sold_kg)

                    # consume_weight_from_product(product, sold_kg)

                # ✅ CASE 2: Normal unit sale (sausage)
                else:
                    item.unit_price = product.wholesale_price if stype == "wholesale" else product.unit_price

                    if product.is_weighted:
                        # If weighted product but user didn’t choose weight size, block it
                        raise ValueError(f"{product.name} is weighted. Please select a weight size.")
                    if qty > product.quantity:
                        raise ValueError(f"Not enough stock for {product.name}. Available: {product.quantity}")

                    product.quantity = max(0, product.quantity - qty)
                    product.save(update_fields=["quantity"])

                item.save()
                subtotal += item.line_total()

            # totals
            discount = Decimal(sale.discount or Decimal("0.00"))
            after_discount = max(Decimal("0.00"), subtotal - discount)

            apply_vat = bool(sale.apply_vat)
            vat = (after_discount * VAT_RATE).quantize(Decimal("0.01")) if apply_vat else Decimal("0.00")
            grand = (after_discount + vat).quantize(Decimal("0.01"))

            sale.subtotal_amount = after_discount
            sale.vat_amount = vat
            sale.total_amount = grand
            sale.save(update_fields=["subtotal_amount", "vat_amount", "total_amount"])

            # credit
            if sale.is_credit:
                amount_paid = Decimal(sale_form.cleaned_data.get("amount_paid") or Decimal("0.00"))
                amount_paid = max(Decimal("0.00"), min(amount_paid, grand))

                if amount_paid > 0:
                    CreditPayment.objects.create(
                        sale=sale,
                        amount=amount_paid,
                        payment_method="cash",
                        reference="",
                        received_by=request.user,
                    )

                sale.recalc_credit(save=True)
            else:
                # fully paid
                sale.amount_paid = sale.total_amount
                sale.save(update_fields=["amount_paid"])

            return redirect("sale_receipt", sale_id=sale.id)

    else:
        sale_form = SaleForm()
        formset = ItemFormset()

    return render(request, "sales/create_sale.html", {
        "sale_form": sale_form,
        "formset": formset,
        "sale_type": stype,
        "weights_json": json.dumps(weights_json),
         "products_json": json.dumps(products_json),  # ✅ ADD THIS
    })
    
    
 

@login_required
@has_any_group("SuperAdmin", "SubAdmin","Admin", "Staff", "Retail", "Wholesale")
def sale_list(request):
    qs = Sale.objects.all().order_by("-timestamp")

    # ✅ Keep your existing role filtering
    if request.user.groups.filter(name="Wholesale").exists():
        qs = qs.filter(sale_type="wholesale")
    elif request.user.groups.filter(name="Retail").exists():
        qs = qs.filter(sale_type="retail")

    # ---------------------------
    # Filters (GET)
    # ---------------------------
    q = (request.GET.get("q") or "").strip()
    start = (request.GET.get("start") or "").strip()    # YYYY-MM-DD
    end = (request.GET.get("end") or "").strip()        # YYYY-MM-DD
    preset = (request.GET.get("preset") or "").strip()  # today | week | month | all
    per_page = request.GET.get("per_page") or "10"

    # Search by customer name/phone
    if q:
        qs = qs.filter(
            Q(customer_name__icontains=q) |
            Q(customer_phone__icontains=q)
        )

    # Date presets
    now = timezone.localtime()
    today = now.date()

    if preset == "today":
        qs = qs.filter(timestamp__date=today)

    elif preset == "week":
        start_date = today - timedelta(days=6)
        qs = qs.filter(timestamp__date__gte=start_date, timestamp__date__lte=today)

    elif preset == "month":
        start_date = today - timedelta(days=29)
        qs = qs.filter(timestamp__date__gte=start_date, timestamp__date__lte=today)

    elif preset == "all":
        pass

    else:
        # Custom dates
        try:
            if start:
                start_date = datetime.strptime(start, "%Y-%m-%d").date()
                qs = qs.filter(timestamp__date__gte=start_date)
            if end:
                end_date = datetime.strptime(end, "%Y-%m-%d").date()
                qs = qs.filter(timestamp__date__lte=end_date)
        except ValueError:
            pass

    # Per-page safety
    try:
        per_page_int = int(per_page)
        if per_page_int not in (10, 25, 50, 100):
            per_page_int = 10
    except ValueError:
        per_page_int = 10

    # ✅ Pagination (IMPORTANT: don't name variable "paginator" if you imported Paginator)
    p = Paginator(qs, per_page_int)
    page_number = request.GET.get("page") or 1
    page_obj = p.get_page(page_number)

    return render(request, "sales/sale_list.html", {
        "sales": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "start": start,
        "end": end,
        "preset": preset,
        "per_page": per_page_int,
        "total_count": p.count,
    })
# def sale_list(request):
#     qs = Sale.objects.all().order_by("-timestamp")
#     # qs = visible_queryset_for_user(qs, request.user)

#     if request.user.groups.filter(name="Wholesale").exists():
#         qs = qs.filter(sale_type="wholesale")
#     elif request.user.groups.filter(name="Retail").exists():
#         qs = qs.filter(sale_type="retail")

#     return render(request, "sales/sale_list.html", {"sales": qs})


@login_required
@has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
def credit_sales_list(request):
    # compute balance at DB level
    balance_expr = ExpressionWrapper(
        F("total_amount") - F("amount_paid"),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )

    qs = Sale.objects.filter(is_credit=True).annotate(balance_due_db=balance_expr).filter(balance_due_db__gt=0).order_by("-timestamp")

    if request.user.groups.filter(name="Wholesale").exists():
        qs = qs.filter(sale_type="wholesale")
    elif request.user.groups.filter(name="Retail").exists():
        qs = qs.filter(sale_type="retail")

    total_outstanding = qs.aggregate(s=Sum("balance_due_db"))["s"] or Decimal("0.00")

    return render(request, "sales/credit_sales_list.html", {
        "sales": qs,
        "total_outstanding": total_outstanding,
    })


@login_required
@has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
@transaction.atomic
def credit_payment_add(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id, is_credit=True)

    if request.user.groups.filter(name="Wholesale").exists() and sale.sale_type != "wholesale":
        return redirect("credit_sales_list")
    if request.user.groups.filter(name="Retail").exists() and sale.sale_type != "retail":
        return redirect("credit_sales_list")

    if request.method == "POST":
        form = CreditPaymentForm(request.POST)
        if form.is_valid():
            pay = form.save(commit=False)

            # cap to remaining balance
            remaining = sale.balance_due_calc
            if pay.amount > remaining:
                pay.amount = remaining

            pay.sale = sale
            pay.received_by = request.user
            pay.save()  # triggers sale.recalc_credit(save=True)

            return redirect("credit_sales_list")
    else:
        form = CreditPaymentForm()

    return render(request, "sales/credit_payment_add.html", {"sale": sale, "form": form})
def receipt_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    items = sale.items.all()

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=landscape(A5))
    width, height = landscape(A5)

    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width/2, height - 20, "❄️ FRESH CHILL COLD STORE ❄️")
    p.setFont("Helvetica", 9)
    p.drawCentredString(width/2, height - 34, "Accra - Ghana | Tel: +233 54 000 0000")

    y = height - 56
    p.setFont("Helvetica", 8)
    p.drawString(20, y, f"Date: {sale.timestamp.strftime('%Y-%m-%d %H:%M')}")
    p.drawRightString(width - 20, y, f"Receipt: CS-{sale.id:04d}")
    y -= 14

    cashier = sale.created_by.get_full_name() if sale.created_by and sale.created_by.get_full_name() else (sale.created_by.username if sale.created_by else "—")
    p.drawString(20, y, f"Cashier: {cashier}")
    y -= 12
    p.drawString(20, y, f"Customer: {sale.customer_name or 'Walk-in Customer'}")
    y -= 12
    p.drawString(20, y, f"Payment: {sale.get_payment_method_display()}")

    y -= 18
    p.setFont("Helvetica-Bold", 9)
    p.drawString(20, y, "Item")
    p.drawRightString(220, y, "Qty")
    p.drawRightString(290, y, "Price (₵)")
    p.drawRightString(370, y, "Total (₵)")
    p.line(15, y-2, width-15, y-2)
    y -= 12
    p.setFont("Helvetica", 9)

    for it in items:
        name = it.product.name if it.product else "Deleted Product"
        if it.weight_price:
            name = f"{name} ({it.weight_price.size_kg}kg)"

        p.drawString(20, y, name[:32])
        p.drawRightString(220, y, str(it.quantity))
        p.drawRightString(290, y, f"{float(it.unit_price):.2f}")
        p.drawRightString(370, y, f"{float(it.line_total()):.2f}")
        y -= 12
        if y < 70:
            p.showPage()
            y = height - 40
            p.setFont("Helvetica", 9)

    y -= 6
    p.line(15, y, width-15, y)
    y -= 14

    p.drawRightString(320, y, "Subtotal:")
    p.drawRightString(370, y, f"₵{float(sale.subtotal_amount):.2f}")
    y -= 12

    if sale.apply_vat:
        p.drawRightString(320, y, "VAT (4%):")
        p.drawRightString(370, y, f"₵{float(sale.vat_amount):.2f}")
        y -= 12

    p.setFont("Helvetica-Bold", 10)
    p.drawRightString(320, y, "Total:")
    p.drawRightString(370, y, f"₵{float(sale.total_amount):.2f}")

    # QR
    try:
        qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{float(sale.total_amount):.2f}|Date:{sale.timestamp.strftime('%Y-%m-%d %H:%M')}"
        qr = qrcode.make(qr_text)
        buf = BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)
        p.drawInlineImage(buf, width - 120, 20, width=80, height=80)
    except Exception:
        pass

    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(width/2, 18, "Thank you for your purchase! — Fresh Chill Cold Store")

    p.showPage()
    p.save()

    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="receipt_{sale.id}.pdf"'
    return response


def sale_receipt(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    items = sale.items.all()

    qr_base64 = ""
    try:
        qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{float(sale.total_amount):.2f}|Date:{sale.timestamp.strftime('%Y-%m-%d %H:%M')}"
        qr_img = qrcode.make(qr_text)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        qr_base64 = base64.b64encode(buf.read()).decode("ascii")
        buf.close()
    except Exception:
        qr_base64 = ""

    return render(request, "sales/receipt.html", {
        "sale": sale,
        "items": items,
        "subtotal": sale.subtotal_amount,
        "discount": sale.discount,
        "subtotal_after_discount": sale.subtotal_amount,
        "vat": sale.vat_amount,
        "grand_total": sale.total_amount,
        "qr_base64": qr_base64,
    })


# """# sales/views.py
# from decimal import Decimal
# import json
# from io import BytesIO
# import base64
# from urllib import request
# import qrcode

# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib.auth.decorators import login_required
# from django.forms import formset_factory
# from django.db import transaction
# from django.db.models import Sum, F, ExpressionWrapper, DecimalField

# # from sales.utils import visible_queryset_for_user
# from users.utils import has_any_group
# from .models import Sale, SaleItem, CreditPayment, VAT_RATE
# from .forms import SaleForm, SaleItemForm, CreditPaymentForm
# from inventory.models import Product, SaleableWeightSize

# from django.http import HttpResponse
# from reportlab.lib.pagesizes import A5, landscape
# from reportlab.pdfgen import canvas


# def user_sale_type(user):
#     if user.groups.filter(name="Wholesale").exists():
#         return "wholesale"
#     if user.groups.filter(name="Retail").exists():
#         return "retail"
#     return "retail"


# @login_required
# @has_any_group("Admin", "Staff", "Retail", "Wholesale")
# @transaction.atomic
# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)
#     stype = user_sale_type(request.user)

#     # ✅ Build weights json for frontend
#     weights = {}
#     for p in Product.objects.all():
#         sizes = SaleableWeightSize.objects.filter(product=p).order_by("size_kg")
#         weights[str(p.id)] = [
#             {
#                 "id": s.id,
#                 "label": f"{s.size_kg}kg",
#                 "size_kg": str(s.size_kg),
#                 "retail_price": float(s.retail_price or 0),
#                 "wholesale_price": float(s.wholesale_price or 0),
#             }
#             for s in sizes
#         ]

#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)

#         if sale_form.is_valid() and formset.is_valid():
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.sale_type = stype
#             sale.is_credit = (sale_form.cleaned_data.get("payment_method") == "credit")
#             sale.apply_vat = bool(sale_form.cleaned_data.get("apply_vat"))
#             sale.save()

#             subtotal = Decimal("0.00")

#             # save items
#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale
#                     product = item.product

#                     # ✅ FORCE server-side unit_price
#                     if getattr(product, "track_method", "unit") == "boxed_weight":
#                         size = item.weight_size
#                         if not size:
#                             raise ValueError("Weight size missing for boxed-weight product.")

#                         if sale.sale_type == "wholesale":
#                             item.unit_price = size.wholesale_price or Decimal("0.00")
#                         else:
#                             item.unit_price = size.retail_price or Decimal("0.00")

#                     else:
#                         if sale.sale_type == "wholesale":
#                             item.unit_price = product.wholesale_price or Decimal("0.00")
#                         else:
#                             item.unit_price = product.unit_price or Decimal("0.00")

#                     item.save()
#                     subtotal += item.line_total()

#             discount = sale_form.cleaned_data.get("discount") or Decimal("0.00")
#             subtotal_after_discount = subtotal - Decimal(discount)
#             if subtotal_after_discount < Decimal("0.00"):
#                 subtotal_after_discount = Decimal("0.00")

#             # ✅ VAT optional
#             vat = Decimal("0.00")
#             if sale.apply_vat:
#                 vat = (subtotal_after_discount * VAT_RATE).quantize(Decimal("0.01"))

#             grand = (subtotal_after_discount + vat).quantize(Decimal("0.01"))

#             sale.subtotal_amount = subtotal_after_discount
#             sale.vat_amount = vat
#             sale.total_amount = grand
#             sale.due_date = sale_form.cleaned_data.get("due_date")
#             sale.save(update_fields=["subtotal_amount", "vat_amount", "total_amount", "due_date", "apply_vat"])

#             # credit initial payment
#             if sale.is_credit:
#                 amount_paid = sale_form.cleaned_data.get("amount_paid") or Decimal("0.00")
#                 amount_paid = Decimal(amount_paid)

#                 if amount_paid < Decimal("0.00"):
#                     amount_paid = Decimal("0.00")
#                 if amount_paid > sale.total_amount:
#                     amount_paid = sale.total_amount

#                 if amount_paid > Decimal("0.00"):
#                     CreditPayment.objects.create(
#                         sale=sale,
#                         amount=amount_paid,
#                         payment_method="cash",
#                         reference="",
#                         received_by=request.user,
#                     )

#                 sale.recalc_credit(save=True)

#             else:
#                 # non-credit fully paid
#                 sale.amount_paid = sale.total_amount
#                 sale.save(update_fields=["amount_paid"])

#             return redirect("sale_receipt", sale_id=sale.id)

#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()

#     return render(request, "sales/create_sale.html", {
#         "sale_form": sale_form,
#         "formset": formset,
#         "sale_type": stype,
#         "weights_json": json.dumps(weights),
#     })
    
    
# @login_required
# @has_any_group("SuperAdmin", "SubAdmin","Admin", "Staff", "Retail", "Wholesale")
# def sale_list(request):
#     qs = Sale.objects.all().order_by("-timestamp")
#     qs = visible_queryset_for_user(qs, request.user)

#     if request.user.groups.filter(name="Wholesale").exists():
#         qs = qs.filter(sale_type="wholesale")
#     elif request.user.groups.filter(name="Retail").exists():
#         qs = qs.filter(sale_type="retail")

#     return render(request, "sales/sale_list.html", {"sales": qs})

# @login_required
# @has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
# def credit_sales_list(request):
#     qs = Sale.objects.filter(is_credit=True)

# # ✅ visibility filter
#     qs = visible_queryset_for_user(qs, request.user)
#     balance_expr = ExpressionWrapper(
#         F("total_amount") - F("amount_paid"),
#         output_field=DecimalField(max_digits=12, decimal_places=2)
#     )

#     qs = Sale.objects.filter(is_credit=True).annotate(balance_due_db=balance_expr).filter(balance_due_db__gt=0).order_by("-timestamp")

#     if request.user.groups.filter(name="Wholesale").exists():
#         qs = qs.filter(sale_type="wholesale")
#     elif request.user.groups.filter(name="Retail").exists():
#         qs = qs.filter(sale_type="retail")

#     total_outstanding = qs.aggregate(s=Sum("balance_due_db"))["s"] or Decimal("0.00")

#     return render(request, "sales/credit_sales_list.html", {
#         "sales": qs,
#         "total_outstanding": total_outstanding,
#     })



# @login_required
# @has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
# @transaction.atomic
# def credit_payment_add(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id, is_credit=True)

#     if request.user.groups.filter(name="Wholesale").exists() and sale.sale_type != "wholesale":
#         return redirect("credit_sales_list")
#     if request.user.groups.filter(name="Retail").exists() and sale.sale_type != "retail":
#         return redirect("credit_sales_list")

#     if request.method == "POST":
#         form = CreditPaymentForm(request.POST)
#         if form.is_valid():
#             pay = form.save(commit=False)

#             # cap to remaining
#             remaining = sale.balance_due_calc
#             if pay.amount > remaining:
#                 pay.amount = remaining

#             pay.sale = sale
#             pay.received_by = request.user
#             pay.save()

#             sale.recalc_credit(save=True)
#             return redirect("credit_sales_list")
#     else:
#         form = CreditPaymentForm()

#     return render(request, "sales/credit_payment_add.html", {"sale": sale, "form": form})
# """



# """# sales/views.py
from decimal import Decimal
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.db import transaction
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from decimal import Decimal, ROUND_HALF_UP

from users.utils import has_any_group
from .models import Sale, SaleItem, CreditPayment
from .forms import SaleForm, SaleItemForm, CreditPaymentForm
from inventory.models import Product
from django.http import HttpResponse
from reportlab.lib.pagesizes import A5, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
import json
from io import BytesIO
from django.utils import timezone
from datetime import datetime, date
# with QR code generation
import qrcode
import base64

VAT_RATE = Decimal("0.15")


def user_sale_type(user):
    if user.groups.filter(name="Wholesale").exists():
        return "wholesale"
    if user.groups.filter(name="Retail").exists():
        return "retail"
    return "retail"


@login_required
@has_any_group("Admin", "Staff", "Retail", "Wholesale")
@transaction.atomic
def create_sale(request):
    ItemFormset = formset_factory(SaleItemForm, extra=1)
    stype = user_sale_type(request.user)

    products = Product.objects.all()
    prices_json = {
        p.id: float(p.wholesale_price if stype == "wholesale" else p.unit_price)
        for p in products
    }

    if request.method == "POST":
        sale_form = SaleForm(request.POST)
        formset = ItemFormset(request.POST)

        if sale_form.is_valid() and formset.is_valid():
            sale = sale_form.save(commit=False)
            sale.created_by = request.user
            sale.sale_type = stype
            sale.is_credit = (sale_form.cleaned_data.get("payment_method") == "credit")
            sale.amount_paid = Decimal("0.00")

            # save early to get sale.id for items
            sale.save()

            subtotal = Decimal("0.00")

            for f in formset:
                if f.cleaned_data and f.cleaned_data.get("product"):
                    item = f.save(commit=False)
                    item.sale = sale

                    # force server-side price
                    if sale.sale_type == "wholesale":
                        item.unit_price = item.product.wholesale_price or Decimal("0.00")
                    else:
                        item.unit_price = item.product.unit_price or Decimal("0.00")

                    item.save()
                    subtotal += item.line_total()

            discount = sale_form.cleaned_data.get("discount") or Decimal("0.00")
            discount = Decimal(discount)

            subtotal_after_discount = subtotal - discount
            if subtotal_after_discount < Decimal("0.00"):
                subtotal_after_discount = Decimal("0.00")

            # vat = (subtotal_after_discount * VAT_RATE).quantize(Decimal("0.01"))
            # grand = (subtotal_after_discount + vat).quantize(Decimal("0.01"))
            
            apply_vat = sale_form.cleaned_data.get("apply_vat", True)
            vat = (subtotal_after_discount * VAT_RATE).quantize(Decimal("0.01")) if apply_vat else Decimal("0.00")
            grand = (subtotal_after_discount + vat).quantize(Decimal("0.01"))

            sale.apply_vat = apply_vat
            sale.subtotal_amount = subtotal_after_discount
            sale.vat_amount = vat
            sale.total_amount = grand
            sale.due_date = sale_form.cleaned_data.get("due_date")
            sale.save(update_fields=["apply_vat", "subtotal_amount", "vat_amount", "total_amount", "due_date"])
            
            
            # sale.subtotal_amount = subtotal_after_discount
            # sale.vat_amount = vat
            # sale.total_amount = grand
            # sale.due_date = sale_form.cleaned_data.get("due_date")

            # sale.save(update_fields=["subtotal_amount", "vat_amount", "total_amount", "due_date"])

            # CREDIT handling
            if sale.is_credit:
                amount_paid = sale_form.cleaned_data.get("amount_paid") or Decimal("0.00")
                amount_paid = Decimal(amount_paid)

                if amount_paid < Decimal("0.00"):
                    amount_paid = Decimal("0.00")
                if amount_paid > grand:
                    amount_paid = grand

                if amount_paid > Decimal("0.00"):
                    CreditPayment.objects.create(
                        sale=sale,
                        amount=amount_paid,
                        payment_method="cash",
                        reference="",
                        received_by=request.user,
                    )

                sale.recalc_credit(save=True)
            else:
                # non-credit => fully paid
                sale.amount_paid = sale.total_amount
                sale.is_credit = False
                sale.save(update_fields=["amount_paid", "is_credit"])

            return redirect("sale_receipt", sale_id=sale.id)

    else:
        sale_form = SaleForm()
        formset = ItemFormset()

    return render(request, "sales/create_sale.html", {
        "sale_form": sale_form,
        "formset": formset,
        "prices_json": json.dumps(prices_json),
        "sale_type": stype,
    })


@login_required
@has_any_group("Admin", "Staff", "Retail", "Wholesale")
def sale_list(request):
    qs = Sale.objects.all().order_by("-timestamp")

    if request.user.groups.filter(name="Wholesale").exists():
        qs = qs.filter(sale_type="wholesale")
    elif request.user.groups.filter(name="Retail").exists():
        qs = qs.filter(sale_type="retail")

    return render(request, "sales/sale_list.html", {"sales": qs})


@login_required
@has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
def credit_sales_list(request):
     
    #Outstanding credit sales list (based on DB calculation).
    
    balance_expr = ExpressionWrapper(
        F("total_amount") - F("amount_paid"),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )

    qs = (
        Sale.objects.filter(is_credit=True)
        .annotate(balance_due_db=balance_expr)
        .filter(balance_due_db__gt=0)
        .order_by("-timestamp")
    )

    if request.user.groups.filter(name="Wholesale").exists():
        qs = qs.filter(sale_type="wholesale")
    elif request.user.groups.filter(name="Retail").exists():
        qs = qs.filter(sale_type="retail")

    total_outstanding = qs.aggregate(s=Sum("balance_due_db"))["s"] or Decimal("0.00")

    return render(request, "sales/credit_sales_list.html", {
        "sales": qs,
        "total_outstanding": total_outstanding,
    })


@login_required
@has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
@transaction.atomic
def credit_payment_add(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id, is_credit=True)

    # scope protection
    if request.user.groups.filter(name="Wholesale").exists() and sale.sale_type != "wholesale":
        return redirect("credit_sales_list")
    if request.user.groups.filter(name="Retail").exists() and sale.sale_type != "retail":
        return redirect("credit_sales_list")

    # already paid?
    if sale.balance_due_calc <= Decimal("0.00"):
        sale.is_credit = False
        sale.save(update_fields=["is_credit"])
        return redirect("credit_sales_list")

    if request.method == "POST":
        form = CreditPaymentForm(request.POST)
        if form.is_valid():
            pay = form.save(commit=False)

            remaining = sale.balance_due_calc
            if pay.amount > remaining:
                pay.amount = remaining

            pay.sale = sale
            pay.received_by = request.user
            pay.save()  # triggers sale.recalc_credit(save=True)

            return redirect("credit_sales_list")
    else:
        form = CreditPaymentForm()

    return render(request, "sales/credit_payment_add.html", {
        "sale": sale,
        "form": form,
        "remaining": sale.balance_due_calc,
    })



# from decimal import Decimal
# import json
# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib.auth.decorators import login_required
# from django.forms import formset_factory
# from django.db import transaction
# from django.db.models import Sum

# from users.utils import has_any_group
# from .models import Sale, SaleItem, CreditPayment
# from .forms import SaleForm, SaleItemForm, CreditPaymentForm
# from inventory.models import Product
# from django.http import HttpResponse
# from reportlab.lib.pagesizes import A5, landscape
# from reportlab.pdfgen import canvas
# from reportlab.lib.units import mm
# from reportlab.lib import colors
# import json
# from io import BytesIO
# from django.utils import timezone
# from datetime import datetime
# # with QR code generation
# import qrcode
# import base64

# VAT_RATE = Decimal("0.15")


# def user_sale_type(user):
#     if user.groups.filter(name="Wholesale").exists():
#         return "wholesale"
#     if user.groups.filter(name="Retail").exists():
#         return "retail"
#     return "retail"


# @login_required
# @has_any_group("Admin", "Staff", "Retail", "Wholesale")
# @transaction.atomic
# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)
#     stype = user_sale_type(request.user)

#     products = Product.objects.all()
#     prices_json = {
#         p.id: float(p.wholesale_price if stype == "wholesale" else p.unit_price)
#         for p in products
#     }

#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)

#         if sale_form.is_valid() and formset.is_valid():
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.sale_type = stype

#             # credit?
#             sale.is_credit = (sale_form.cleaned_data.get("payment_method") == "credit")
#             sale.save()

#             subtotal = Decimal("0.00")

#             # Save items
#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale

#                     # Force correct price
#                     if sale.sale_type == "wholesale":
#                         item.unit_price = item.product.wholesale_price or Decimal("0.00")
#                     else:
#                         item.unit_price = item.product.unit_price or Decimal("0.00")

#                     item.save()
#                     subtotal += item.line_total()

#             discount = sale_form.cleaned_data.get("discount") or Decimal("0.00")
#             discount = Decimal(discount)

#             subtotal_after_discount = subtotal - discount
#             if subtotal_after_discount < Decimal("0.00"):
#                 subtotal_after_discount = Decimal("0.00")

#             vat = (subtotal_after_discount * VAT_RATE).quantize(Decimal("0.01"))
#             grand = (subtotal_after_discount + vat).quantize(Decimal("0.01"))

#             sale.subtotal_amount = subtotal_after_discount
#             sale.vat_amount = vat
#             sale.total_amount = grand
#             sale.due_date = sale_form.cleaned_data.get("due_date")

#             sale.save()

#             # If credit, record initial payment (if any)
#             if sale.is_credit:
#                 amount_paid = sale_form.cleaned_data.get("amount_paid") or Decimal("0.00")
#                 amount_paid = Decimal(amount_paid)

#                 if amount_paid < Decimal("0.00"):
#                     amount_paid = Decimal("0.00")
#                 if amount_paid > grand:
#                     amount_paid = grand

#                 if amount_paid > Decimal("0.00"):
#                     CreditPayment.objects.create(
#                         sale=sale,
#                         amount=amount_paid,
#                         payment_method="cash",
#                         reference="",
#                         received_by=request.user,
#                     )

#                 # Recalc paid/balance from payments
#                 sale.recalc_credit()
#                 sale.save()

#             else:
#                 # Not credit => fully paid
#                 sale.amount_paid = sale.total_amount
#                 sale.balance_due = Decimal("0.00")
#                 sale.save()

#             return redirect("sale_receipt", sale_id=sale.id)

#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()

#     return render(request, "sales/create_sale.html", {
#         "sale_form": sale_form,
#         "formset": formset,
#         "prices_json": json.dumps(prices_json),
#         "sale_type": stype,
#     })


# # @login_required
# # @has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
# # def credit_sales_list(request):
# #     """
# #     Shows credit sales that still have balance due.
# #     Retail users see retail credits, wholesale users see wholesale credits,
# #     Admin/Staff/Accountant can see all.
# #     """
# #     # qs = Sale.objects.filter(is_credit=True, balance_due_calc__gt=0).order_by("-timestamp")   replaced with the one below on 27/12/2025
# #     from django.db.models import F, ExpressionWrapper, DecimalField
# #     balance_expr = ExpressionWrapper(
# #         F("total_amount") - F("amount_paid"),
# #         output_field=DecimalField(max_digits=12, decimal_places=2)
# #     )

# #     qs = Sale.objects.filter(is_credit=True).annotate(balance_due_db=balance_expr).filter(balance_due_db__gt=0).order_by("-timestamp")
 
# #     # has been replaced with the one just above it due to mismatch of balance due calculation on 27/12/2025
    
# #     if request.user.groups.filter(name="Wholesale").exists():
# #         qs = qs.filter(sale_type="wholesale")
# #     elif request.user.groups.filter(name="Retail").exists():
# #         qs = qs.filter(sale_type="retail")
        
        
# #         # replaced just now with the one below on 27/12/2025
# #     total_outstanding = qs.aggregate(s=Sum("balance_due_db"))["s"] or Decimal("0.00")    

# #     # total_outstanding = qs.aggregate(s=Sum("balance_due"))["s"] or Decimal("0.00")

# #     return render(request, "sales/credit_sales_list.html", {
# #         "sales": qs,
# #         "total_outstanding": total_outstanding,
# #     })

# from decimal import Decimal
# from django.db import transaction
# from django.shortcuts import get_object_or_404, redirect, render
# from django.contrib.auth.decorators import login_required
# from users.utils import has_any_group
# from .models import Sale
# from .forms import CreditPaymentForm

# @login_required
# @has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
# @transaction.atomic
# def credit_payment_add(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id, is_credit=True)

#     # protect scope
#     if request.user.groups.filter(name="Wholesale").exists() and sale.sale_type != "wholesale":
#         return redirect("credit_sales_list")
#     if request.user.groups.filter(name="Retail").exists() and sale.sale_type != "retail":
#         return redirect("credit_sales_list")

#     # ✅ if already fully paid, just bounce back
#     if sale.balance_due_calc <= Decimal("0.00"):
#         sale.is_credit = False
#         sale.save(update_fields=["is_credit"])
#         return redirect("credit_sales_list")

#     if request.method == "POST":
#         form = CreditPaymentForm(request.POST)
#         if form.is_valid():
#             pay = form.save(commit=False)

#             remaining = sale.balance_due_calc

#             # cap payment to remaining balance
#             if pay.amount > remaining:
#                 pay.amount = remaining

#             pay.sale = sale
#             pay.received_by = request.user
#             pay.save()  # this triggers sale.recalc_credit(save=True) in CreditPayment.save()

#             # ✅ optional: refresh sale instance so you see latest amount_paid/is_credit
#             sale.refresh_from_db()

#             return redirect("credit_sales_list")
#     else:
#         form = CreditPaymentForm()

#     return render(request, "sales/credit_payment_add.html", {
#         "sale": sale,
#         "form": form,
#         "remaining": sale.balance_due_calc,  # optional for template display
#     })



# @login_required
# @has_any_group("Admin", "Staff", "Accountant", "Retail", "Wholesale")
# @transaction.atomic
# def credit_payment_add(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id, is_credit=True)

#     # protect scope
#     if request.user.groups.filter(name="Wholesale").exists() and sale.sale_type != "wholesale":
#         return redirect("credit_sales_list")
#     if request.user.groups.filter(name="Retail").exists() and sale.sale_type != "retail":
#         return redirect("credit_sales_list")

#     if request.method == "POST":
#         form = CreditPaymentForm(request.POST)
#         if form.is_valid():
#             pay = form.save(commit=False)

#             # cap payment to remaining balance
#             if pay.amount > sale.balance_due:
#                 pay.amount = sale.balance_due

#             pay.sale = sale
#             pay.received_by = request.user
#             pay.save()

#             # recalc totals from payments
#             sale.recalc_credit()

#             # If paid off, optional: flip payment_method to cash/momo/card? (keep credit for history)
#             if sale.balance_due <= Decimal("0.00"):
#                 sale.balance_due = Decimal("0.00")

#             sale.save()

#             return redirect("credit_sales_list")
#     else:
#         form = CreditPaymentForm()

#     return render(request, "sales/credit_payment_add.html", {
#         "sale": sale,
#         "form": form,
#     })



# @login_required
# @has_any_group("Admin", "Staff", "Retail", "Wholesale")
# def sale_list(request):
#     qs = Sale.objects.all().order_by("-timestamp")

#     if request.user.groups.filter(name="Wholesale").exists():
#         qs = qs.filter(sale_type="wholesale")
#     elif request.user.groups.filter(name="Retail").exists():
#         qs = qs.filter(sale_type="retail")

#     return render(request, "sales/sale_list.html", {"sales": qs})


# @login_required
#
# """
# def receipt_view(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id)
#     items = SaleItem.objects.filter(sale=sale)

#     buffer = BytesIO()
#     p = canvas.Canvas(buffer, pagesize=landscape(A5))
#     width, height = landscape(A5)

#     # header
#     p.setFont("Helvetica-Bold", 14)
#     p.drawCentredString(width/2, height - 20, "❄️ FRESH CHILL COLD STORE ❄️")
#     p.setFont("Helvetica", 9)
#     p.drawCentredString(width/2, height - 34, "Accra - Ghana | Tel: +233 54 000 0000")

#     # details
#     y = height - 56
#     p.setFont("Helvetica", 8)
#     p.drawString(20, y, f"Date: {sale.timestamp.strftime('%Y-%m-%d %H:%M')}")
#     p.drawRightString(width - 20, y, f"Receipt: CS-{sale.id:04d}")
#     y -= 14
#     cashier = sale.created_by.get_full_name() if sale.created_by and sale.created_by.get_full_name() else (sale.created_by.username if sale.created_by else '—')
#     p.drawString(20, y, f"Cashier: {cashier}")
#     y -= 12
#     p.drawString(20, y, f"Customer: {sale.customer_name or 'Walk-in Customer'}")
#     y -= 12
#     p.drawString(20, y, f"Payment: {sale.get_payment_method_display() if hasattr(sale, 'get_payment_method_display') else sale.payment_method}")

#     # table header
#     y -= 18
#     p.setFont("Helvetica-Bold", 9)
#     p.drawString(20, y, "Item")
#     p.drawRightString(200, y, "Qty")
#     p.drawRightString(260, y, "Price (₵)")
#     p.drawRightString(340, y, "Total (₵)")
#     p.line(15, y-2, width-15, y-2)
#     y -= 12
#     p.setFont("Helvetica", 9)

#     subtotal = 0
#     for it in items:
#         name = (it.product.name[:28] + '...') if it.product and len(it.product.name) > 31 else (it.product.name if it.product else "Deleted Product")
#         p.drawString(20, y, name)
#         p.drawRightString(200, y, str(it.quantity))
#         p.drawRightString(260, y, f"{float(it.unit_price):.2f}")
#         line_total = float(it.line_total())
#         p.drawRightString(340, y, f"{line_total:.2f}")
#         subtotal += line_total
#         y -= 12
#         if y < 60:
#             p.showPage()
#             y = height - 40
#             p.setFont("Helvetica", 9)

#     # totals (VAT 15%)
#     y -= 6
#     p.line(15, y, width-15, y)
#     y -= 14
#     p.drawRightString(300, y, "Subtotal:")
#     p.drawRightString(340, y, f"₵{subtotal:.2f}")
#     y -= 12
#     vat = round(subtotal * 0.15, 2)
#     p.drawRightString(300, y, "VAT (15%):")
#     p.drawRightString(340, y, f"₵{vat:.2f}")
#     y -= 12
#     grand = subtotal + vat
#     p.setFont("Helvetica-Bold", 10)
#     p.drawRightString(300, y, "Total:")
#     p.drawRightString(340, y, f"₵{grand:.2f}")

#     # QR code (optional) - embed on page bottom-right
#     try:
#         qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{grand:.2f}|Date:{sale.timestamp.strftime('%Y-%m-%d %H:%M')}"
#         qr = qrcode.make(qr_text)
#         qr_buffer = BytesIO()
#         qr.save(qr_buffer, format='PNG')
#         qr_buffer.seek(0)
#         img_x = width - 120
#         img_y = 20
#         p.drawInlineImage(qr_buffer, img_x, img_y, width=80, height=80)
#     except Exception:
#         pass

#     # footer
#     p.setFont("Helvetica-Oblique", 8)
#     p.drawCentredString(width/2, 18, "Thank you for your purchase! — Fresh Chill Cold Store")

#     p.showPage()
#     p.save()

#     pdf = buffer.getvalue()
#     buffer.close()
#     response = HttpResponse(pdf, content_type='application/pdf')
#     response['Content-Disposition'] = f'inline; filename="receipt_{sale.id}.pdf"'
#     return response


# VAT_RATE = Decimal("0.15")


# def sale_receipt(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id)
#     items = sale.items.all()

#     subtotal = sum((it.line_total() for it in items), Decimal("0.00"))
#     discount = sale.discount or Decimal("0.00")
#     subtotal_after_discount = max(Decimal("0.00"), subtotal - discount)

#     vat = (subtotal_after_discount * VAT_RATE).quantize(Decimal("0.01")) if sale.apply_vat else Decimal("0.00")
#     grand_total = (subtotal_after_discount + vat).quantize(Decimal("0.01"))

#     # QR base64 (unchanged)
#     qr_base64 = ""
#     try:
#         qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{grand_total:.2f}|Date:{sale.timestamp.strftime('%Y-%m-%d %H:%M')}"
#         qr_img = qrcode.make(qr_text)
#         buf = BytesIO()
#         qr_img.save(buf, format="PNG")
#         buf.seek(0)
#         qr_base64 = base64.b64encode(buf.read()).decode("ascii")
#         buf.close()
#     except Exception:
#         qr_base64 = ""

#     return render(request, "sales/receipt.html", {
#         "sale": sale,
#         "items": items,
#         "subtotal": subtotal,
#         "discount": discount,
#         "subtotal_after_discount": subtotal_after_discount,
#         "vat": vat,
#         "grand_total": grand_total,
#         "qr_base64": qr_base64,
#     })
# """
# # def sale_receipt(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id)
#     items = sale.items.all()

#     subtotal = sum((it.line_total() for it in items), Decimal("0.00"))
#     discount = sale.discount or Decimal("0.00")
#     subtotal_after_discount = max(Decimal("0.00"), subtotal - discount)
    

#     # vat = (subtotal_after_discount * VAT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
#     # grand_total = (subtotal_after_discount + vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
#     # updated on 30/12/2025 to include apply_vat field
#      vat = (subtotal_after_discount * VAT_RATE).quantize(Decimal("0.01")) if apply_vat else Decimal("0.00")
#      grand = (subtotal_after_discount + vat).quantize(Decimal("0.01"))
#     # QR base64
#     qr_base64 = ""
#     try:
#         qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{grand_total}|Date:{sale.timestamp:%Y-%m-%d %H:%M}"
#         qr_img = qrcode.make(qr_text)
#         buf = BytesIO()
#         qr_img.save(buf, format="PNG")
#         buf.seek(0)
#         qr_base64 = base64.b64encode(buf.read()).decode("ascii")
#     finally:
#         try:
#             buf.close()
#         except Exception:
#             pass

#     return render(request, "sales/receipt.html", {
#         "sale": sale,
#         "items": items,
#         "subtotal": subtotal,
#         "discount": discount,
#         "subtotal_after_discount": subtotal_after_discount,
#         "vat": vat,
#         "grand_total": grand_total,
#         "qr_base64": qr_base64,
#     })


# # @login_required
# def sale_receipt(request, sale_id):
#     """
#     HTML receipt view — nicer printable page in browser.
#     Provides subtotal, VAT, grand total, and a base64 QR image (qr_base64).
#     """
#     sale = get_object_or_404(Sale, id=sale_id)
#     items = sale.items.all()

#     # Calculate subtotal using line_total()
#     subtotal = sum([float(it.line_total()) for it in items])
#     discount = float(sale.discount or 0)
#     subtotal_after_discount = max(0.0, subtotal - discount)

#     vat = round(subtotal_after_discount * 0.15, 2)
#     grand_total = round(subtotal_after_discount + vat, 2)

#     # generate QR base64 for inline image
#     qr_base64 = ""
#     try:
#         qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{grand_total:.2f}|Date:{sale.timestamp.strftime('%Y-%m-%d %H:%M')}"
#         qr_img = qrcode.make(qr_text)
#         buf = BytesIO()
#         qr_img.save(buf, format='PNG')
#         buf.seek(0)
#         qr_base64 = base64.b64encode(buf.read()).decode('ascii')
#         buf.close()
#     except Exception:
#         qr_base64 = ""

#     return render(request, "sales/receipt.html", {
#         "sale": sale,
#         "items": items,
#         "subtotal": subtotal,
#         "discount": discount,
#         "subtotal_after_discount": subtotal_after_discount,
#         "vat": vat,
#         "grand_total": grand_total,
#         "qr_base64": qr_base64,
#     })

#  just added this for check something right and maybe revert back later
# from decimal import Decimal
# import json
# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib.auth.decorators import login_required
# from django.forms import formset_factory
# from users.utils import has_any_group
# from .models import Sale, SaleItem, CreditPayment
# from .forms import SaleForm, SaleItemForm, CreditPaymentForm
# from inventory.models import Product
# from django.http import HttpResponse
# from reportlab.lib.pagesizes import A5, landscape
# from reportlab.pdfgen import canvas
# from reportlab.lib.units import mm
# from reportlab.lib import colors
# import json
# from io import BytesIO
# from django.utils import timezone
# from datetime import datetime
# # with QR code generation
# import qrcode
# import base64


# VAT_RATE = Decimal("0.15")

# def user_sale_type(user):
#     # Admin can do anything, but for now we choose:
#     # Retail group => retail, Wholesale group => wholesale, else retail
#     if user.groups.filter(name="Wholesale").exists():
#         return "wholesale"
#     if user.groups.filter(name="Retail").exists():
#         return "retail"
#     return "retail"

# @login_required
# @has_any_group("Admin", "Staff", "Retail", "Wholesale")
# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)
#     stype = user_sale_type(request.user)

#     products = Product.objects.all()
#     prices_json = {
#         p.id: float(p.wholesale_price if stype == "wholesale" else p.unit_price)
#         for p in products
#     }

#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)

#         if sale_form.is_valid() and formset.is_valid():
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.sale_type = stype
#             sale.is_credit = (sale_form.cleaned_data.get("payment_method") == "credit")
#             sale.amount_paid = Decimal("0.00")  # default for non-credit and credit too
#             sale.due_date = None
#             sale.save()

#             subtotal = Decimal("0.00")

#             # save items
#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale

#                     # ✅ force server-side price
#                     if sale.sale_type == "wholesale":
#                         item.unit_price = item.product.wholesale_price
#                     else:
#                         item.unit_price = item.product.unit_price

#                     item.save()
#                     subtotal += item.line_total()

#             # totals
#             discount = sale_form.cleaned_data.get("discount") or Decimal("0.00")
#             discount = Decimal(discount)

#             subtotal_after_discount = subtotal - discount
#             if subtotal_after_discount < Decimal("0.00"):
#                 subtotal_after_discount = Decimal("0.00")

#             vat = (subtotal_after_discount * VAT_RATE).quantize(Decimal("0.01"))
#             grand = (subtotal_after_discount + vat).quantize(Decimal("0.01"))

#             # credit fields
#             amount_paid = sale_form.cleaned_data.get("amount_paid") or Decimal("0.00")
#             amount_paid = Decimal(amount_paid)

#             if amount_paid < Decimal("0.00"):
#                 amount_paid = Decimal("0.00")

#             if amount_paid > grand:
#                 amount_paid = grand

#             sale.subtotal_amount = subtotal_after_discount
#             sale.vat_amount = vat
#             sale.total_amount = grand
#             sale.amount_paid = amount_paid
#             sale.balance_due = (grand - amount_paid).quantize(Decimal("0.01"))
#             sale.due_date = sale_form.cleaned_data.get("due_date")
#             sale.save()

#             # ✅ if paid something now and it is credit, store it as a payment record
#             if sale.is_credit and amount_paid > Decimal("0.00"):
#                 CreditPayment.objects.create(
#                     sale=sale,
#                     amount=amount_paid,
#                     payment_method="cash",  # you can extend SaleForm to capture "paid_via" if you want
#                     reference="",
#                     received_by=request.user
#                 )

#             return redirect("sale_receipt", sale_id=sale.id)

#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()

#     return render(request, "sales/create_sale.html", {
#         "sale_form": sale_form,
#         "formset": formset,
#         "prices_json": json.dumps(prices_json),
#         "sale_type": stype,
#     })
# # ) Add pages to track credit + receive payments
# # ✅ 1) A “Credit Sales” list (outstanding)
# @login_required
# @has_any_group("Admin", "Staff", "Accountant")
# def credit_sales_list(request):
#     qs = Sale.objects.filter(is_credit=True).order_by("-timestamp")
#     qs = qs.filter(balance_due__gt=Decimal("0.00"))
#     return render(request, "sales/credit_sales_list.html", {"sales": qs})

# # ✅ 2) Receive payment for a credit sale
# @login_required
# @has_any_group("Admin", "Staff", "Accountant")
# def credit_payment_add(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id, is_credit=True)

#     if request.method == "POST":
#         form = CreditPaymentForm(request.POST)
#         if form.is_valid():
#             p = form.save(commit=False)
#             p.sale = sale
#             p.received_by = request.user
#             p.save()

#             # update sale paid/balance
#             sale.amount_paid = (sale.amount_paid + p.amount).quantize(Decimal("0.01"))
#             if sale.amount_paid > sale.total_amount:
#                 sale.amount_paid = sale.total_amount
#             sale.balance_due = (sale.total_amount - sale.amount_paid).quantize(Decimal("0.01"))
#             sale.save()

#             return redirect("sale_receipt", sale_id=sale.id)

#     else:
#         form = CreditPaymentForm()

#     return render(request, "sales/credit_payment_add.html", {"sale": sale, "form": form})

# @login_required
# @has_any_group("Admin", "Staff", "Retail", "Wholesale")
# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)

#     stype = user_sale_type(request.user)

#     # ✅ pick correct price list for the logged-in user
#     products = Product.objects.all()
#     if stype == "wholesale":
#         prices_json = {p.id: float(p.wholesale_price) for p in products}
#     else:
#         prices_json = {p.id: float(p.unit_price) for p in products}

#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)

#         if sale_form.is_valid() and formset.is_valid():
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.sale_type = stype
#             sale.save()

#             subtotal = Decimal("0.00")

#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale

#                     # ✅ FORCE correct unit price from product (don’t trust posted value)
#                     if sale.sale_type == "wholesale":
#                         item.unit_price = item.product.wholesale_price
#                     else:
#                         item.unit_price = item.product.unit_price

#                     item.save()
#                     subtotal += item.line_total()

#             discount = sale_form.cleaned_data.get("discount") or Decimal("0.00")
#             subtotal_after_discount = subtotal - Decimal(discount)
#             if subtotal_after_discount < 0:
#                 subtotal_after_discount = Decimal("0.00")

#             vat = (subtotal_after_discount * VAT_RATE)
#             grand = subtotal_after_discount + vat

#             sale.subtotal_amount = subtotal_after_discount
#             sale.vat_amount = vat
#             sale.total_amount = grand
#             sale.save()

#             # ✅ Redirect to printable HTML receipt (better UX)
#             return redirect("sale_receipt", sale_id=sale.id)
#         # add to track error  if the form is not valid
#         else:
#             print("SALE FORM ERRORS:", sale_form.errors)
#             print("FORMSET ERRORS:", formset.errors)
#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()

#     return render(request, "sales/create_sale.html", {
#         "sale_form": sale_form,
#         "formset": formset,
#         "prices_json": json.dumps(prices_json),
#         "sale_type": stype,
#     },
# )







# from decimal import Decimal
# from django.shortcuts import render, redirect
# from django.contrib.auth.decorators import login_required
# from .models import Sale, SaleItem
# from .forms import SaleForm, SaleItemForm
# from inventory.models import Product
# from django.forms import formset_factory
# from users.utils import has_any_group
# from django.shortcuts import render, get_object_or_404
# from django.http import HttpResponse
# from reportlab.lib.pagesizes import A5, landscape
# from reportlab.pdfgen import canvas
# from reportlab.lib.units import mm
# from reportlab.lib import colors
# import json
# from io import BytesIO
# from django.utils import timezone
# from datetime import datetime
# # with QR code generation
# import qrcode
# import base64

# commented out on 20/12/2025 it has been replaced
# 
# @login_required
# @has_any_group("Admin", "Staff")
# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)

#     # collect product prices for JS auto-fill
#     products = Product.objects.all()
#     prices_json = {p.id: float(p.unit_price) for p in products}

#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)
        
#         if sale_form.is_valid() and formset.is_valid():
#              # --- Create Sale ---
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.save()

#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale
#                     item.save()

#     # redirect straight to receipt page
#         # if sale: 
#             return redirect("receipt_view", sale_id=sale.id)



#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()

#     return render(
#         request,
#         "sales/create_sale.html",
#         {
#             "sale_form": sale_form,
#             "formset": formset,
#             "prices_json": json.dumps(prices_json),
#         },
#     )
    
# @login_required
# @has_any_group("Admin", "Staff")
# 
# # commented out on 20/12/2025 it has been replaced

# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)

#     # Send product prices to JS
#     products = Product.objects.all()
#     prices_json = {p.id: float(p.unit_price) for p in products}

#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)

#         if sale_form.is_valid() and formset.is_valid():

#             # --- Create Sale ---
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.total_amount = 0
#             sale.save()

#             subtotal = 0

#             # --- Save Items ---
#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale
#                     item.save()
#                     subtotal += item.line_total()

#             # --- Apply Discount ---
#             discount = Decimal(str(sale_form.cleaned_data.get("discount") or 0))
#             subtotal = Decimal(str(subtotal))
            
#             subtotal -= discount
#             if subtotal < 0:
#                 subtotal = Decimal("0.00")

#             # --- VAT 15% ---
#             vat = subtotal * Decimal("0.15")
#             grand_total = subtotal + vat

#             # Save final total
#             sale.total_amount = grand_total
#             sale.save()

#             # Redirect correctly
#             return redirect("receipt_view", sale_id=sale.id)

#         else:
#             print("SALE FORM ERRORS:", sale_form.errors)
#             print("FORMSET ERRORS:", formset.errors)

#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()

#     return render(
#         request,
#         "sales/create_sale.html",
#         {
#             "sale_form": sale_form,
#             "formset": formset,
#             "prices_json": json.dumps(prices_json),
#         },
#     )
    

# @login_required
# @has_any_group("Admin", "Staff") 
# 
# commented out on 20/12/2025 it has been replaced
# 
# def sale_list(request):
#     sales = Sale.objects.all().order_by('-timestamp') 
#     return render(request, "sales/sale_list.html", {"sales": sales})


# pasted out on 26/12/2025 it has been replaced. I wanted to keep it just in case cause i haev added credit and debot feature





# def receipt_view(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id)
#     items = SaleItem.objects.filter(sale=sale)

#     buffer = BytesIO()
#     p = canvas.Canvas(buffer, pagesize=landscape(A5))
#     width, height = landscape(A5)

#     # header
#     p.setFont("Helvetica-Bold", 14)
#     p.drawCentredString(width/2, height - 20, "❄️ FRESH CHILL COLD STORE ❄️")
#     p.setFont("Helvetica", 9)
#     p.drawCentredString(width/2, height - 34, "Accra - Ghana | Tel: +233 54 000 0000")

#     # details
#     y = height - 56
#     p.setFont("Helvetica", 8)
#     p.drawString(20, y, f"Date: {sale.timestamp.strftime('%Y-%m-%d %H:%M')}")
#     p.drawRightString(width - 20, y, f"Receipt: CS-{sale.id:04d}")
#     y -= 14
#     p.drawString(20, y, f"Cashier: {sale.created_by.get_full_name() if sale.created_by else sale.created_by.username if sale.created_by else '—'}")
#     y -= 12
#     p.drawString(20, y, f"Customer: {sale.customer_name or 'Walk-in Customer'}")
#     y -= 12
#     p.drawString(20, y, f"Payment: {sale.get_payment_method_display() if hasattr(sale, 'get_payment_method_display') else sale.payment_method}")

#     # table header
#     y -= 18
#     p.setFont("Helvetica-Bold", 9)
#     p.drawString(20, y, "Item")
#     p.drawRightString(200, y, "Qty")
#     p.drawRightString(260, y, "Price (₵)")
#     p.drawRightString(340, y, "Total (₵)")
#     p.line(15, y-2, width-15, y-2)
#     y -= 12
#     p.setFont("Helvetica", 9)

#     total = 0
#     for it in items:
#         name = (it.product.name[:28] + '...') if len(it.product.name) > 31 else it.product.name
#         p.drawString(20, y, name)
#         p.drawRightString(200, y, str(it.quantity))
#         p.drawRightString(260, y, f"{float(it.unit_price):.2f}")
#         p.drawRightString(340, y, f"{float(it.total_price):.2f}")
#         total += float(it.total_price)
#         y -= 12
#         if y < 60:
#             p.showPage()
#             y = height - 40
#             p.setFont("Helvetica", 9)

#     # totals
#     y -= 6
#     p.line(15, y, width-15, y)
#     y -= 14
#     p.drawRightString(300, y, "Subtotal:")
#     p.drawRightString(340, y, f"₵{total:.2f}")
#     y -= 12
#     vat = round(total * 0.05, 2)
#     p.drawRightString(300, y, "VAT (5%):")
#     p.drawRightString(340, y, f"₵{vat:.2f}")
#     y -= 12
#     grand = total + vat
#     p.setFont("Helvetica-Bold", 10)
#     p.drawRightString(300, y, "Total:")
#     p.drawRightString(340, y, f"₵{grand:.2f}")

#     # QR code (optional) - embed on page bottom-right
#     try:
#         qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{grand:.2f}|Date:{sale.timestamp.strftime('%Y-%m-%d %H:%M')}"
#         qr = qrcode.make(qr_text)
#         qr_buffer = BytesIO()
#         qr.save(qr_buffer, format='PNG')
#         qr_buffer.seek(0)
#         # place image (x,y from bottom-left)
#         img_x = width - 120
#         img_y = 20
#         p.drawInlineImage(qr_buffer, img_x, img_y, width=80, height=80)
#     except Exception:
#         # if qrcode not available or fails, ignore silently
#         pass

#     # footer
#     p.setFont("Helvetica-Oblique", 8)
#     p.drawCentredString(width/2, 18, "Thank you for your purchase! — Fresh Chill Cold Store")

#     p.showPage()
#     p.save()

#     pdf = buffer.getvalue()
#     buffer.close()
#     response = HttpResponse(pdf, content_type='application/pdf')
#     response['Content-Disposition'] = f'inline; filename="receipt_{sale.id}.pdf"'
#     return response

#@login_required
# @has_any_group("Admin", "Staff")
# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)

#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)

#         if sale_form.is_valid() and formset.is_valid():
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.save()

#             subtotal = 0

#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale
#                     item.save()
#                     subtotal += item.quantity * item.unit_price

#             # Apply discount if available
#             discount = sale_form.cleaned_data.get("discount") or 0
#             total = subtotal - float(discount)

#             sale.total_amount = total
#             sale.save()

#             return redirect("sale_receipt", sale_id=sale.id)

#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()

#     return render(request, "sales/create_sale.html", {"sale_form": sale_form,"formset": formset})

 
# @login_required
# @has_any_group("Admin", "Staff")
# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)

#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)

#         if sale_form.is_valid() and formset.is_valid():
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.save()

#             total = 0
#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale
#                     item.save()
#                     total += item.quantity * item.unit_price

#             sale.total_amount = total
#             sale.save()

#             return redirect("sale_receipt", sale_id=sale.id)

#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()

#     return render(request, "sales/create_sale.html", {
#         "sale_form": sale_form,
#         "formset": formset
#     })

# def create_sale(request):
#     ItemFormset = formset_factory(SaleItemForm, extra=1)
#     if request.method == "POST":
#         sale_form = SaleForm(request.POST)
#         formset = ItemFormset(request.POST)
#         if sale_form.is_valid() and formset.is_valid():
#             sale = sale_form.save(commit=False)
#             sale.created_by = request.user
#             sale.save()
#             total = 0
#             for f in formset:
#                 if f.cleaned_data and f.cleaned_data.get("product"):
#                     item = f.save(commit=False)
#                     item.sale = sale
#                     item.save()
#                     total += item.quantity * item.unit_price
#             sale.total_amount = total
#             sale.save()
#             return redirect("inventory_dashboard")
#     else:
#         sale_form = SaleForm()
#         formset = ItemFormset()
#     return render(request, "sales/create_sale.html", {"sale_form": sale_form, "formset": formset})
# # for receipt generation
# 
# 
# 
# @login_required
# def sale_receipt(request, sale_id):
#     sale = get_object_or_404(Sale, id=sale_id)
#     items = sale.items.all()
#     return render(request, "sales/receipt.html", {"sale": sale, "items": items})
# 