# inventory/forms.py
from decimal import Decimal
from django import forms

from .models import Product, StockEntry, StockOut, ProductWeightPrice


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "track_method",
            "name", "sku", "category",
            "unit_price", "wholesale_price",
            "is_weighted",
            "box_weight_kg", "boxes_in_stock", "box_remaining_kg",
            "quantity", "min_quantity_alert",
            "image",
        ]

    def clean(self):
        cleaned = super().clean()
        is_weighted = cleaned.get("is_weighted")
        track_method = cleaned.get("track_method")

        box_weight = cleaned.get("box_weight_kg") or Decimal("0.00")
        boxes = cleaned.get("boxes_in_stock") or 0
        br = cleaned.get("box_remaining_kg") or Decimal("0.00")
        qty = cleaned.get("quantity") or 0

        # If boxed_weight, force is_weighted
        if track_method == "boxed_weight":
            is_weighted = True
            cleaned["is_weighted"] = True

        if is_weighted:
            # weighted product rules
            if box_weight <= 0:
                self.add_error("box_weight_kg", "Box weight must be greater than 0 for weighted products.")
            if boxes < 0:
                self.add_error("boxes_in_stock", "Boxes in stock cannot be negative.")
            if br < 0:
                self.add_error("box_remaining_kg", "Box remaining kg cannot be negative.")

            # optional: you can auto-zero unit quantity to avoid confusion
            # cleaned["quantity"] = 0
        else:
            # non-weighted product rules
            if qty < 0:
                self.add_error("quantity", "Quantity cannot be negative.")
            # If not weighted, keep boxed fields clean (optional)
            # cleaned["boxes_in_stock"] = 0
            # cleaned["box_remaining_kg"] = Decimal("0.00")

        return cleaned


class StockEntryForm(forms.ModelForm):
    class Meta:
        model = StockEntry
        fields = ["product", "quantity", "unit_price", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ only allow normal unit products
        self.fields["product"].queryset = Product.objects.filter(is_weighted=False, track_method="unit")

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity") or 0
        if qty <= 0:
            raise forms.ValidationError("Quantity must be greater than 0.")
        return qty


class StockOutForm(forms.ModelForm):
    class Meta:
        model = StockOut
        fields = ["product", "quantity", "reason"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ only allow normal unit products
        self.fields["product"].queryset = Product.objects.filter(is_weighted=False, track_method="unit")

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity") or 0
        if qty <= 0:
            raise forms.ValidationError("Quantity must be greater than 0.")
        return qty


class ProductWeightPriceForm(forms.ModelForm):
    """
    Optional helper form if you create/update weight sizes in UI.
    """
    class Meta:
        model = ProductWeightPrice
        fields = ["product", "weight_kg", "retail_price", "wholesale_price", "is_active"]

    def clean_weight_kg(self):
        w = self.cleaned_data.get("weight_kg") or Decimal("0.00")
        if w <= 0:
            raise forms.ValidationError("Weight must be greater than 0.")
        return w


# from django import forms
# from .models import Product, StockEntry, StockOut

# class ProductForm(forms.ModelForm):
#     class Meta:
#         model = Product
#         fields = "__all__"

# class StockEntryForm(forms.ModelForm):
#     class Meta:
#         model = StockEntry
#         fields = ["product", "quantity", "unit_price", "notes"]

# class StockOutForm(forms.ModelForm):
#     class Meta:
#         model = StockOut
#         fields = ["product", "quantity", "reason"]
