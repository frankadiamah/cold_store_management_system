from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import F
from django.db.models import F, Q
from django.core.paginator import Paginator
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from users.utils import has_any_group
from .models import Product, StockEntry, StockOut
from .forms import ProductForm, StockEntryForm, StockOutForm


# 🧊 Dashboard (View-only for Admin, Staff, Accountant)
# @login_required
# @has_any_group("Admin", "Staff", "Accountant")
def dashboard(request):
    products = Product.objects.all().order_by("category", "-quantity")
    low_stock = products.filter(quantity__lte=F('min_quantity_alert'))
    context = {"products": products, "low_stock": low_stock}
    return render(request, "inventory/dashboard.html", context)

class ProductListView(ListView):
    model = Product
    template_name = "inventory/product_list.html"
    context_object_name = "products"
    paginate_by = 12  # change per-page count here

    def get_queryset(self):
        qs = Product.objects.select_related('category').all().order_by('category__name', '-quantity')

        q = self.request.GET.get('q', "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(sku__icontains=q) |
                Q(category__name__icontains=q)
            )

        filter_mode = self.request.GET.get('filter')  # values: low, high, all (default)
        if filter_mode == 'low':
            qs = qs.filter(quantity__lte=F('min_quantity_alert'))
        elif filter_mode == 'high':
            # treat "high" as quantity greater than min alert (you can adjust logic)
            qs = qs.filter(quantity__gt=F('min_quantity_alert'))

        # category filter by id
        category_id = self.request.GET.get('category')
        if category_id:
            try:
                cid = int(category_id)
                qs = qs.filter(category_id=cid)
            except ValueError:
                pass
            
        
        
        # price range filter
        min_price = self.request.GET.get('min_price')
        max_price = self.request.GET.get('max_price')

        def clean_decimal(value):
            try:
                return Decimal(value)
            except (InvalidOperation, TypeError):
                return None

        min_val = clean_decimal(min_price)
        max_val = clean_decimal(max_price)

        if min_val is not None:
            qs = qs.filter(unit_price__gte=min_val)

        if max_val is not None:
            qs = qs.filter(unit_price__lte=max_val)    
            try:
                cid = int(category_id)
                qs = qs.filter(category_id=cid)
            except ValueError:
                pass

        # price range filter
        
        # min_price = self.request.GET.get('min_price')
        # max_price = self.request.GET.get('max_price')
        # if min_price:
        #     try:
        #         qs = qs.filter(unit_price__gte=float(min_price))
        #     except ValueError:
        #         pass
        # if max_price:
        #     try:
        #         qs = qs.filter(unit_price__lte=float(max_price))
        #     except ValueError:
        #         pass

        # sorting (optional)
        sort = self.request.GET.get('sort')
        if sort == 'price_asc':
            qs = qs.order_by('unit_price')
        elif sort == 'price_desc':
            qs = qs.order_by('-unit_price')

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # pass categories for filter UI
        context['categories'] = Product._meta.model.objects.none()
        try:
            from .models import Category
            context['categories'] = Category.objects.all()
        except Exception:
            context['categories'] = []

        # keep current query params to preserve state in template links
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        context['query_string'] = params.urlencode()
        context['current_q'] = self.request.GET.get('q', '')
        context['current_filter'] = self.request.GET.get('filter', '')
        context['current_category'] = self.request.GET.get('category', '')
        context['min_price'] = self.request.GET.get('min_price', '')
        context['max_price'] = self.request.GET.get('max_price', '')
        context['sort'] = self.request.GET.get('sort', '')
        return context
    
    # replace the previous ProductListView with this updated one above it
# 🧩 List of products
# class ProductListView(ListView):
#     model = Product
#     template_name = "inventory/product_list.html"
#     context_object_name = "products"


# 🧾 Add new product
@login_required
@has_any_group("Admin", "Staff")
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':

        product.delete()

        # AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"status": "success"})

        messages.success(request, "Product deleted successfully.")
        return redirect('product_list')

    return redirect('product_list')
# replace previous ProductCreateView with this function-based view
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Product added successfully!")
            return redirect("product_list")
        else:
            messages.error(request, "❌ Failed to add product. Please check the details.")
    else:
        form = ProductForm()
    return render(request, "inventory/product_form.html", {"form": form, "title": "Add Product"})

# def product_create(request):
#     if request.method == "POST":
#         form = ProductForm(request.POST)
#         if form.is_valid():
#             form.save()
#             messages.success(request, "Product added successfully.")
#             return redirect("product_list")
#     else:
#         form = ProductForm()

#     return render(request, "inventory/product_form.html", {"form": form, "title": "Add Product"})



# 🧮 Stock In
@login_required
@has_any_group("Admin", "Staff")
def stock_in(request):
    if request.method == "POST":
        form = StockEntryForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, f"📦 Stock-in recorded for {obj.product.name}")
            return redirect("inventory_dashboard")
        else:
            messages.error(request, "❌ Error: Invalid input while adding stock-in.")
    else:
        form = StockEntryForm()
    return render(request, "inventory/stock_in.html", {"form": form})


# 📉 Stock Out
@login_required
@has_any_group("Admin", "Staff")
def stock_out(request):
    if request.method == "POST":
        form = StockOutForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, f"📤 Stock-out recorded for {obj.product.name}")
            return redirect("inventory_dashboard")
        else:
            messages.error(request, "❌ Error: Could not process stock-out entry.")
    else:
        form = StockOutForm()
    return render(request, "inventory/stock_out.html", {"form": form})


# ✏️ Edit Product
@login_required
@has_any_group("Admin", "Staff")
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"✅ Product '{product.name}' updated successfully!")
            return redirect("product_list")
        else:
            messages.error(request, "❌ Could not update product. Please check inputs.")
    else:
        form = ProductForm(instance=product)
    return render(request, "inventory/product_form.html", {"form": form})


# 🗑️ Delete Product due to too much of them. 
# @login_required
# @has_any_group("Admin", "Staff")
# def product_delete(request, pk):
#     product = get_object_or_404(Product, pk=pk)
#     if request.method == "POST":
#         messages.success(request, f"🗑️ Product '{product.name}' deleted successfully.")
#         product.delete()
#         return redirect("product_list")
#     return render(request, "inventory/product_confirm_delete.html", {"product": product})


# 📝 Edit Stock Entry
@login_required
@has_any_group("Admin", "Staff")
def stock_entry_edit(request, pk):
    entry = get_object_or_404(StockEntry, pk=pk)
    if request.method == "POST":
        form = StockEntryForm(request.POST, instance=entry)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, f"🧾 Stock Entry updated for {obj.product.name}")
            return redirect("inventory_dashboard")
        else:
            messages.error(request, "❌ Failed to update stock entry.")
    else:
        form = StockEntryForm(instance=entry)
    return render(request, "inventory/stock_in.html", {"form": form})


# 🧾 Edit Stock Out
@login_required
@has_any_group("Admin", "Staff")
def stock_out_edit(request, pk):
    out = get_object_or_404(StockOut, pk=pk)
    if request.method == "POST":
        form = StockOutForm(request.POST, instance=out)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, f"🧾 Stock Out updated for {obj.product.name}")
            return redirect("inventory_dashboard")
        else:
            messages.error(request, "❌ Could not update stock-out.")
    else:
        form = StockOutForm(instance=out)
    return render(request, "inventory/stock_out.html", {"form": form})





"""✅ What This Version Adds
Feature	Benefit
✅ Toast messages	User sees success/error instantly
✅ Group restrictions	Admin/Staff/Accountant separation
✅ Consistent redirects	No broken navigation
✅ Emojis for clarity	Easy to read success messages
✅ Cleaner error handling	Prevents silent failures
✅ Reusable and extendable	Future features fit easily"""






# from django.shortcuts import render, redirect, get_object_or_404
# from django.views.generic import ListView, CreateView
# from django.contrib.auth.decorators import login_required
# from .models import Product, StockEntry, StockOut
# from .forms import ProductForm, StockEntryForm, StockOutForm
# from django.urls import reverse_lazy
# from django.db.models import F
# from users.utils import has_any_group

# @login_required
# @has_any_group("Admin","Staff")
# def dashboard(request):
#     products = Product.objects.all().order_by("category", "-quantity")
#     low_stock = products.filter(quantity__lte=F('min_quantity_alert'))
#     context = {"products": products, "low_stock": low_stock}
#     return render(request, "inventory/dashboard.html", context)

# class ProductListView(ListView):
#     model = Product
#     template_name = "inventory/product_list.html"
#     context_object_name = "products"

# class ProductCreateView(CreateView):
#     model = Product
#     form_class = ProductForm
#     template_name = "inventory/product_form.html"
#     success_url = reverse_lazy("product_list")

# @login_required
# def stock_in(request):
#     if request.method == "POST":
#         form = StockEntryForm(request.POST)
#         if form.is_valid():
#             obj = form.save(commit=False)
#             obj.created_by = request.user
#             obj.save()
#             return redirect("inventory_dashboard")
#     else:
#         form = StockEntryForm()
#     return render(request, "inventory/stock_in.html", {"form": form})

# @login_required
# def stock_out(request):
#     if request.method == "POST":
#         form = StockOutForm(request.POST)
#         if form.is_valid():
#             obj = form.save(commit=False)
#             obj.created_by = request.user
#             obj.save()
#             return redirect("inventory_dashboard")
#     else:
#         form = StockOutForm()
#     return render(request, "inventory/stock_out.html", {"form": form})

# """Apply @has_any_group("Admin","Staff") to:

# stock_in

# stock_out

# ProductCreateView (use GroupRequiredMixin for class views if needed)

# Apply @has_any_group("Admin","Staff","Accountant") to:

# inventory_dashboard (read)

# reports views (Accountant included)"""
# # for possible future use on deleting N editing entries/products: on products and stock entries/outs 
# @login_required
# def product_edit(request, pk):
#     product = get_object_or_404(Product, pk=pk)
#     if request.method == "POST":
#         form = ProductForm(request.POST, instance=product)
#         if form.is_valid():
#             form.save()
#             return redirect("product_list")
#     else:
#         form = ProductForm(instance=product)
#     return render(request, "inventory/product_form.html", {"form": form})

# @login_required
# def product_delete(request, pk):
#     product = get_object_or_404(Product, pk=pk)
#     if request.method == "POST":
#         product.delete()
#         return redirect("product_list")
#     return render(request, "inventory/product_confirm_delete.html", {"product": product})

# @login_required
# def stock_entry_edit(request, pk):
#     entry = get_object_or_404(StockEntry, pk=pk)
#     if request.method == "POST":
#         form = StockEntryForm(request.POST, instance=entry)
#         if form.is_valid():
#             obj = form.save(commit=False)
#             obj.created_by = request.user
#             obj.save()
#             return redirect("inventory_dashboard")
#     else:
#         form = StockEntryForm(instance=entry)
#     return render(request, "inventory/stock_in.html", {"form": form})

# @login_required
# def stock_out_edit(request, pk):
#     out = get_object_or_404(StockOut, pk=pk)
#     if request.method == "POST":
#         form = StockOutForm(request.POST, instance=out)
#         if form.is_valid():
#             obj = form.save(commit=False)
#             obj.created_by = request.user
#             obj.save()
#             return redirect("inventory_dashboard")
#     else:
#         form = StockOutForm(instance=out)
#     return render(request, "inventory/stock_out.html", {"form": form})