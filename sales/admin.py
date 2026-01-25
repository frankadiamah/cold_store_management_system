# from django.contrib import admin
# from .models import Sale, SaleItem, CreditPayment

from django.contrib import admin
from .models import Sale, SaleItem, CreditPayment

# @admin.register(Sale)
# class SaleAdmin(admin.ModelAdmin):
#     list_display = ('id', 'sale_type', 'customer_name', 'customer_phone', 'payment_method', 'apply_vat', 'subtotal_amount', 'vat_amount', 'total_amount', 'is_credit', 'amount_paid', 'balance_due_calc', 'due_date', 'timestamp')
#     list_filter = ('sale_type', 'payment_method', 'apply_vat', 'is_credit', 'timestamp', 'due_date')
#     search_fields = ('customer_name', 'customer_phone', 'id')#     readonly_fields = ('subtotal_amount', 'vat_amount', 'total_amount', 'amount_paid', 'balance_due_calc', 'timestamp')
#     list_editable = ('is_credit', 'due_date')
#     ordering = ('-timestamp',)

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale_type', 'customer_name', 'customer_phone', 'payment_method', 'apply_vat', 'subtotal_amount', 'vat_amount', 'total_amount', 'is_credit', 'amount_paid', 'balance_due_calc', 'due_date', 'timestamp')
    list_filter = ('sale_type', 'payment_method', 'apply_vat', 'is_credit', 'timestamp', 'due_date')
    search_fields = ('customer_name', 'customer_phone', 'id')#     readonly_fields = ('subtotal_amount', 'vat_amount', 'total_amount', 'amount_paid', 'balance_due_calc', 'timestamp')
#     list_editable = ('is_credit', 'due_date')
#     ordering = ('-timestamp',)

# @admin.register(SaleItem)
# class SaleItemAdmin(admin.ModelAdmin):
#     list_display = ('id', 'sale', 'product', 'weight_size', 'quantity', 'unit_price', 'line_total')
#     list_filter = ('product', 'weight_size')
#     search_fields = ('product__name', 'sale__customer_name')
#     readonly_fields = ('line_total',)
#     raw_id_fields = ('sale', 'product', 'weight_size')

@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale', 'product', 'weight_price', 'quantity', 'unit_price', 'line_total_display')
    list_filter = ('product', 'weight_price')
    search_fields = ('product__name', 'sale__customer_name')
    readonly_fields = ('line_total',)
    raw_id_fields = ('sale', 'product', 'weight_price')
    
    def line_total_display(self, obj):
        return f"₵{obj.line_total():,.2f}"
    line_total_display.short_description = "Line Total"

# @admin.register(CreditPayment)
# class CreditPaymentAdmin(admin.ModelAdmin):
#     list_display = ('id', 'sale', 'amount', 'payment_method', 'reference', 'paid_on', 'received_by')
#     list_filter = ('payment_method', 'paid_on', 'received_by')
#     search_fields = ('sale__customer_name', 'reference')#     readonly_fields = ('paid_on',)
#     raw_id_fields = ('sale', 'received_by')
#     ordering = ('-paid_on',)

@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale', 'amount', 'payment_method', 'reference', 'paid_on', 'received_by')
    list_filter = ('payment_method', 'paid_on', 'received_by')
    search_fields = ('sale__customer_name', 'reference')#     readonly_fields = ('paid_on',)
#     raw_id_fields = ('sale', 'received_by')
#     ordering = ('-paid_on',)






    """# sales/admin.py
from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html

from .models import Sale, SaleItem, CreditPayment


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    autocomplete_fields = ["product"]
    readonly_fields = ("line_total_display",)
    fields = ("product", "quantity", "unit_price", "line_total_display")

    def line_total_display(self, obj):
        return f"₵{obj.line_total():,.2f}"
    line_total_display.short_description = "Line Total"


class CreditPaymentInline(admin.TabularInline):
    model = CreditPayment
    extra = 0
    readonly_fields = ("paid_on", "received_by")
    fields = ("amount", "payment_method", "reference", "paid_on", "received_by")


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "timestamp",
        "sale_type",
        "customer_name",
        "payment_method",
        "apply_vat",
        "total_amount",
        "amount_paid",
        "balance_due_display",
        "status_badge",
        "created_by",
    )
    list_filter = ("sale_type", "payment_method", "apply_vat", "timestamp", "is_credit")
    search_fields = ("id", "customer_name", "customer_phone", "created_by__username")
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    readonly_fields = (
        "timestamp",
        "subtotal_amount",
        "vat_amount",
        "total_amount",
        "amount_paid",
        "balance_due_display",
    )

    fieldsets = (
        ("Sale Info", {"fields": ("created_by", "sale_type", "customer_name", "customer_phone", "timestamp")}),
        ("Payment", {"fields": ("payment_method", "apply_vat", "discount", "is_credit", "due_date")}),
        ("Totals", {"fields": ("subtotal_amount", "vat_amount", "total_amount", "amount_paid", "balance_due_display")}),
    )

    inlines = [SaleItemInline, CreditPaymentInline]

    def balance_due_display(self, obj):
        return f"₵{obj.balance_due:,.2f}"
    balance_due_display.short_description = "Balance Due"

    def status_badge(self, obj):
        if obj.is_credit and obj.balance_due > 0:
            return format_html('<span style="padding:2px 8px;border-radius:10px;background:#ffe5e5;color:#b00020;">CREDIT</span>')
        return format_html('<span style="padding:2px 8px;border-radius:10px;background:#e6ffed;color:#0a7a2f;">PAID</span>')
    status_badge.short_description = "Status"


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ("id", "sale", "product", "quantity", "unit_price", "line_total_display")
    list_filter = ("product",)
    search_fields = ("product__name", "sale__id")
    autocomplete_fields = ["product"]

    def line_total_display(self, obj):
        return f"₵{obj.line_total():,.2f}"
    line_total_display.short_description = "Line Total"


@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "sale", "amount", "payment_method", "paid_on", "received_by")
    list_filter = ("payment_method", "paid_on")
    search_fields = ("sale__id", "reference", "received_by__username")
    ordering = ("-paid_on",)

    """
    
    
    
    
    
    # 
    # ✅ This will register everything neatly:

# Sale shows paid/balance/status

# Sale opens and shows inline items + inline payments

# SaleItem shows total

# CreditPayment shows history
    # 
    # 
    # 
    # 
    # 