
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Sale, SaleItem
from .forms import SaleForm, SaleItemForm
from inventory.models import Product
from django.forms import formset_factory
from users.utils import has_any_group
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from reportlab.lib.pagesizes import A5, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
import json
from io import BytesIO
from django.utils import timezone
from datetime import datetime
# with QR code generation
import qrcode
import base64


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
def create_sale(request):
    ItemFormset = formset_factory(SaleItemForm, extra=1)

    # Send product prices to JS
    products = Product.objects.all()
    prices_json = {p.id: float(p.unit_price) for p in products}

    if request.method == "POST":
        sale_form = SaleForm(request.POST)
        formset = ItemFormset(request.POST)

        if sale_form.is_valid() and formset.is_valid():

            # --- Create Sale ---
            sale = sale_form.save(commit=False)
            sale.created_by = request.user
            sale.total_amount = 0
            sale.save()

            subtotal = 0

            # --- Save Items ---
            for f in formset:
                if f.cleaned_data and f.cleaned_data.get("product"):
                    item = f.save(commit=False)
                    item.sale = sale
                    item.save()
                    subtotal += item.line_total()

            # --- Apply Discount ---
            discount = Decimal(str(sale_form.cleaned_data.get("discount") or 0))
            subtotal = Decimal(str(subtotal))
            
            subtotal -= discount
            if subtotal < 0:
                subtotal = Decimal("0.00")

            # --- VAT 15% ---
            vat = subtotal * Decimal("0.15")
            grand_total = subtotal + vat

            # Save final total
            sale.total_amount = grand_total
            sale.save()

            # Redirect correctly
            return redirect("receipt_view", sale_id=sale.id)

        else:
            print("SALE FORM ERRORS:", sale_form.errors)
            print("FORMSET ERRORS:", formset.errors)

    else:
        sale_form = SaleForm()
        formset = ItemFormset()

    return render(
        request,
        "sales/create_sale.html",
        {
            "sale_form": sale_form,
            "formset": formset,
            "prices_json": json.dumps(prices_json),
        },
    )
    

# @login_required
# @has_any_group("Admin", "Staff") 
def sale_list(request):
    sales = Sale.objects.all().order_by('-timestamp') 
    return render(request, "sales/sale_list.html", {"sales": sales})











# @login_required
def receipt_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    items = SaleItem.objects.filter(sale=sale)

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=landscape(A5))
    width, height = landscape(A5)

    # header
    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width/2, height - 20, "❄️ FRESH CHILL COLD STORE ❄️")
    p.setFont("Helvetica", 9)
    p.drawCentredString(width/2, height - 34, "Accra - Ghana | Tel: +233 54 000 0000")

    # details
    y = height - 56
    p.setFont("Helvetica", 8)
    p.drawString(20, y, f"Date: {sale.timestamp.strftime('%Y-%m-%d %H:%M')}")
    p.drawRightString(width - 20, y, f"Receipt: CS-{sale.id:04d}")
    y -= 14
    cashier = sale.created_by.get_full_name() if sale.created_by and sale.created_by.get_full_name() else (sale.created_by.username if sale.created_by else '—')
    p.drawString(20, y, f"Cashier: {cashier}")
    y -= 12
    p.drawString(20, y, f"Customer: {sale.customer_name or 'Walk-in Customer'}")
    y -= 12
    p.drawString(20, y, f"Payment: {sale.get_payment_method_display() if hasattr(sale, 'get_payment_method_display') else sale.payment_method}")

    # table header
    y -= 18
    p.setFont("Helvetica-Bold", 9)
    p.drawString(20, y, "Item")
    p.drawRightString(200, y, "Qty")
    p.drawRightString(260, y, "Price (₵)")
    p.drawRightString(340, y, "Total (₵)")
    p.line(15, y-2, width-15, y-2)
    y -= 12
    p.setFont("Helvetica", 9)

    subtotal = 0
    for it in items:
        name = (it.product.name[:28] + '...') if it.product and len(it.product.name) > 31 else (it.product.name if it.product else "Deleted Product")
        p.drawString(20, y, name)
        p.drawRightString(200, y, str(it.quantity))
        p.drawRightString(260, y, f"{float(it.unit_price):.2f}")
        line_total = float(it.line_total())
        p.drawRightString(340, y, f"{line_total:.2f}")
        subtotal += line_total
        y -= 12
        if y < 60:
            p.showPage()
            y = height - 40
            p.setFont("Helvetica", 9)

    # totals (VAT 15%)
    y -= 6
    p.line(15, y, width-15, y)
    y -= 14
    p.drawRightString(300, y, "Subtotal:")
    p.drawRightString(340, y, f"₵{subtotal:.2f}")
    y -= 12
    vat = round(subtotal * 0.15, 2)
    p.drawRightString(300, y, "VAT (15%):")
    p.drawRightString(340, y, f"₵{vat:.2f}")
    y -= 12
    grand = subtotal + vat
    p.setFont("Helvetica-Bold", 10)
    p.drawRightString(300, y, "Total:")
    p.drawRightString(340, y, f"₵{grand:.2f}")

    # QR code (optional) - embed on page bottom-right
    try:
        qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{grand:.2f}|Date:{sale.timestamp.strftime('%Y-%m-%d %H:%M')}"
        qr = qrcode.make(qr_text)
        qr_buffer = BytesIO()
        qr.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        img_x = width - 120
        img_y = 20
        p.drawInlineImage(qr_buffer, img_x, img_y, width=80, height=80)
    except Exception:
        pass

    # footer
    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(width/2, 18, "Thank you for your purchase! — Fresh Chill Cold Store")

    p.showPage()
    p.save()

    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="receipt_{sale.id}.pdf"'
    return response


@login_required
def sale_receipt(request, sale_id):
    """
    HTML receipt view — nicer printable page in browser.
    Provides subtotal, VAT, grand total, and a base64 QR image (qr_base64).
    """
    sale = get_object_or_404(Sale, id=sale_id)
    items = sale.items.all()

    # Calculate subtotal using line_total()
    subtotal = sum([float(it.line_total()) for it in items])
    discount = float(sale.discount or 0)
    subtotal_after_discount = max(0.0, subtotal - discount)

    vat = round(subtotal_after_discount * 0.15, 2)
    grand_total = round(subtotal_after_discount + vat, 2)

    # generate QR base64 for inline image
    qr_base64 = ""
    try:
        qr_text = f"Receipt:CS-{sale.id:04d}|Amount:₵{grand_total:.2f}|Date:{sale.timestamp.strftime('%Y-%m-%d %H:%M')}"
        qr_img = qrcode.make(qr_text)
        buf = BytesIO()
        qr_img.save(buf, format='PNG')
        buf.seek(0)
        qr_base64 = base64.b64encode(buf.read()).decode('ascii')
        buf.close()
    except Exception:
        qr_base64 = ""

    return render(request, "sales/receipt.html", {
        "sale": sale,
        "items": items,
        "subtotal": subtotal,
        "discount": discount,
        "subtotal_after_discount": subtotal_after_discount,
        "vat": vat,
        "grand_total": grand_total,
        "qr_base64": qr_base64,
    })

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