from django.contrib import admin
from .models import (
    Category,
    Product,
    ProductWeightPrice,
    StockEntry,
    StockOut,
)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name", "sku", "category",
        "track_method", "is_weighted",
        "unit_price", "wholesale_price",
        "quantity",
        "boxes_in_stock", "box_remaining_kg", "box_weight_kg",
        "min_quantity_alert", "created_at",
    )
    list_filter = ("track_method", "is_weighted", "category", "created_at")
    search_fields = ("name", "sku", "category__name")
    readonly_fields = ("created_at", "created_by")
    ordering = ("-created_at",)
    list_editable = ("min_quantity_alert",)


@admin.register(ProductWeightPrice)
class ProductWeightPriceAdmin(admin.ModelAdmin):
    list_display = ("product", "weight_kg", "retail_price", "wholesale_price", "is_active")
    list_filter = ("is_active", "product")
    search_fields = ("product__name",)
    ordering = ("product", "weight_kg")


@admin.register(StockEntry)
class StockEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "quantity", "unit_price", "created_by", "created_at")
    list_filter = ("created_at", "created_by")
    search_fields = ("product__name", "notes")
    ordering = ("-created_at",)


@admin.register(StockOut)
class StockOutAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "quantity", "reason", "created_by", "created_at")
    list_filter = ("reason", "created_at", "created_by")
    search_fields = ("product__name",)
    ordering = ("-created_at",)
