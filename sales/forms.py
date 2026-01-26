# sales/forms.py
from decimal import Decimal
from django import forms
from .models import Sale, SaleItem, CreditPayment
from inventory.models import Product, ProductWeightPrice

class SaleForm(forms.ModelForm):
    amount_paid = forms.DecimalField(required=False, min_value=Decimal("0.00"))
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = Sale
        fields = [
            "customer_name", "customer_phone",
            "payment_method", "discount",
            "apply_vat",
            "amount_paid", "due_date"
        ]

    def clean(self):
        cleaned = super().clean()
        pm = cleaned.get("payment_method")
        amount_paid = cleaned.get("amount_paid") or Decimal("0.00")

        if pm == "credit":
            if amount_paid < Decimal("0.00"):
                self.add_error("amount_paid", "Amount paid cannot be negative.")
        else:
            cleaned["amount_paid"] = Decimal("0.00")
            cleaned["due_date"] = None

        return cleaned


class SaleItemForm(forms.ModelForm):
    weight_price = forms.ModelChoiceField(
        queryset=ProductWeightPrice.objects.filter(is_active=True),
        required=False
    )

    class Meta:
        model = SaleItem
        fields = ["product", "weight_price", "quantity", "unit_price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["product"].queryset = Product.objects.all()
        # self.fields["unit_price"].widget.attrs["readonly"] = "readonly"

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        weight_price = cleaned.get("weight_price")
        qty = cleaned.get("quantity") or 0

        if not product:
            return cleaned

        if qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")

        # If weight option chosen, it must belong to that product
        if weight_price:
            if weight_price.product_id != product.id:
                raise forms.ValidationError("Selected weight size does not belong to the selected product.")
            if not product.is_weighted:
                raise forms.ValidationError("This product is not configured for weight-based sales.")
              # ✅ important: stock check in kg
            total_kg = (Decimal(weight_price.weight_kg) * Decimal(qty)).quantize(Decimal("0.01"))
            available_kg = product.available_weight_kg()
            if total_kg > available_kg:
                raise forms.ValidationError(f"Not enough kg in stock. Available: {available_kg}kg")

        else:
             # unit sale
            if product.is_weighted:
                raise forms.ValidationError("This product is weighted. Please select a weight size.")
            if qty > product.quantity:
                raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")

        return cleaned
            # # normal unit sale: ensure product has enough quantity (only for non-weighted)
            # if not product.is_weighted and qty > product.quantity:
            #     raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")




# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "weight_price", "quantity"]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         self.fields["product"].queryset = Product.objects.all()
#         self.fields["weight_price"].queryset = ProductWeightPrice.objects.filter(is_active=True)

#         self.fields["product"].widget.attrs.update({"class": "product-select"})
#         self.fields["weight_price"].widget.attrs.update({"class": "weight-select"})
#         self.fields["quantity"].widget.attrs.update({"class": "qty-input", "min": "1"})

#     def clean(self):
#         cleaned = super().clean()
#         product = cleaned.get("product")
#         weight_price = cleaned.get("weight_price")
#         qty = cleaned.get("quantity") or 0

#         if product and weight_price and weight_price.product_id != product.id:
#             raise forms.ValidationError("Selected weight size does not belong to the selected product.")

#         if product and weight_price and qty > 0:
#             total_kg = (weight_price.weight_kg * Decimal(qty)).quantize(Decimal("0.01"))
#             available_kg = product.total_kg_available()
#             if total_kg > available_kg:
#                 raise forms.ValidationError(f"Not enough kg in stock. Available: {available_kg}kg")

#         return cleaned


class CreditPaymentForm(forms.ModelForm):
    class Meta:
        model = CreditPayment
        fields = ["amount", "payment_method", "reference"]

    def clean_amount(self):
        amt = self.cleaned_data.get("amount") or Decimal("0.00")
        if amt <= Decimal("0.00"):
            raise forms.ValidationError("Payment amount must be greater than 0.")
        return amt
# """

# # sales/forms.py
# from decimal import Decimal
# from django import forms
# from .models import Sale, SaleItem, CreditPayment
# from inventory.models import Product, SaleableWeightSize


# class SaleForm(forms.ModelForm):
#     amount_paid = forms.DecimalField(required=False, min_value=Decimal("0.00"))
#     due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

#     apply_vat = forms.BooleanField(required=False, initial=False)

#     class Meta:
#         model = Sale
#         fields = [
#             "customer_name",
#             "customer_phone",
#             "payment_method",
#             "discount",
#             "apply_vat",
#             "amount_paid",
#             "due_date",
#         ]

#     def clean(self):
#         cleaned = super().clean()
#         pm = cleaned.get("payment_method")
#         amount_paid = cleaned.get("amount_paid") or Decimal("0.00")

#         if pm != "credit":
#             cleaned["amount_paid"] = Decimal("0.00")
#             cleaned["due_date"] = None

#         if amount_paid < Decimal("0.00"):
#             self.add_error("amount_paid", "Amount paid cannot be negative.")

#         return cleaned


# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "weight_size", "quantity", "unit_price"]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         self.fields["weight_size"].required = False
#         self.fields["weight_size"].queryset = SaleableWeightSize.objects.none()

#         # If product chosen, filter sizes
#         pid = self.data.get(self.add_prefix("product")) or (self.initial.get("product") if self.initial else None)
#         if pid:
#             try:
#                 self.fields["weight_size"].queryset = SaleableWeightSize.objects.filter(product_id=int(pid))
#             except Exception:
#                 pass

#         self.fields["product"].widget.attrs.update({"class": "product-select"})
#         self.fields["weight_size"].widget.attrs.update({"class": "weight-size-select"})
#         self.fields["quantity"].widget.attrs.update({"class": "qty-input"})
#         self.fields["unit_price"].widget.attrs.update({"class": "price-input", "readonly": "readonly"})

#         self.fields["product"].queryset = Product.objects.all()

#     def clean(self):
#         cleaned = super().clean()
#         product = cleaned.get("product")
#         qty = cleaned.get("quantity") or 0

#         if product and getattr(product, "track_method", "unit") == "unit":
#             if qty > product.quantity:
#                 raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")

#         if product and getattr(product, "track_method", "unit") == "boxed_weight":
#             if not cleaned.get("weight_size"):
#                 raise forms.ValidationError("Please select a weight size (5kg/10kg/20kg/30kg).")

#         return cleaned


# class CreditPaymentForm(forms.ModelForm):
#     class Meta:
#         model = CreditPayment
#         fields = ["amount", "payment_method", "reference"]

#     def clean_amount(self):
#         amt = self.cleaned_data.get("amount") or Decimal("0.00")
#         if amt <= Decimal("0.00"):
#             raise forms.ValidationError("Payment amount must be greater than 0.")
#         return amt
# """



# """# sales/forms.py
# from decimal import Decimal
# from django import forms
# from .models import Sale, SaleItem, CreditPayment
# from inventory.models import Product


# class SaleForm(forms.ModelForm):
#     # Only used when payment_method == "credit"
#     amount_paid = forms.DecimalField(required=False, min_value=Decimal("0.00"))
#     due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
#     apply_vat = forms.BooleanField(required=False, initial=False)  # ✅ NEW

#     class Meta:
#         model = Sale
#         fields = ["customer_name", "customer_phone", "payment_method", "discount", "apply_vat", "amount_paid", "due_date"]

#     def clean(self):
#         cleaned = super().clean()
#         pm = cleaned.get("payment_method")
        
#         cleaned["apply_vat"] = bool(cleaned.get("apply_vat"))
#         amount_paid = cleaned.get("amount_paid") or Decimal("0.00")
#         due_date = cleaned.get("due_date")
#          # ✅ ensure apply_vat becomes True/False cleanly

#         if pm == "credit":
#             # optional required due date (enable if client insists)
#             # if not due_date:
#             #     self.add_error("due_date", "Due date is required for credit sales.")
#             if amount_paid < Decimal("0.00"):
#                 self.add_error("amount_paid", "Amount paid cannot be negative.")
#         else:
#             # not credit -> ignore these
#             cleaned["amount_paid"] = Decimal("0.00")
#             cleaned["due_date"] = None

#         return cleaned

# # sales/forms.py
# from django import forms
# from .models import SaleItem
# from inventory.models import SaleableWeightSize

# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "weight_size", "quantity", "unit_price"]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         self.fields["weight_size"].queryset = SaleableWeightSize.objects.none()
#         self.fields["weight_size"].required = False

#         if self.data.get("product"):
#             try:
#                 pid = int(self.data.get("product"))
#                 self.fields["weight_size"].queryset = SaleableWeightSize.objects.filter(product_id=pid)
#             except:
#                 pass

#         self.fields["product"].widget.attrs.update({"class": "product-select"})
#         self.fields["weight_size"].widget.attrs.update({"class": "weight-size-select"})
#         self.fields["quantity"].widget.attrs.update({"class": "qty-input"})
#         self.fields["unit_price"].widget.attrs.update({"class": "price-input", "readonly": "readonly"})
#     def clean(self): #added by not by chatGPT
#         cleaned = super().clean()
#         product = cleaned.get("product")
#         weight_size = cleaned.get("weight_size")
#         qty = cleaned.get("quantity")

#         if product and weight_size:
#             if weight_size.product != product:
#                 raise forms.ValidationError("Selected weight size does not match the product.")

#         if product and qty and qty > product.quantity:
#             raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")
#         return cleaned
# # class SaleItemForm(forms.ModelForm):
# #     class Meta:
# #         model = SaleItem
# #         fields = ["product", "quantity", "unit_price"]

# #     def __init__(self, *args, **kwargs):
# #         super().__init__(*args, **kwargs)

# #         self.fields["product"].widget.attrs.update({"class": "product-select"})
# #         self.fields["quantity"].widget.attrs.update({"class": "qty-input"})
# #         self.fields["unit_price"].widget.attrs.update({"class": "price-input", "readonly": "readonly"})

# #         self.fields["product"].queryset = Product.objects.all()

# #     def clean(self):
# #         cleaned = super().clean()
# #         product = cleaned.get("product")
# #         qty = cleaned.get("quantity")

# #         if product and qty and qty > product.quantity:
# #             raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")
# #         return cleaned


# class CreditPaymentForm(forms.ModelForm):
#     class Meta:
#         model = CreditPayment
#         fields = ["amount", "payment_method", "reference"]

#     def clean_amount(self):
#         amt = self.cleaned_data.get("amount") or Decimal("0.00")
#         if amt <= Decimal("0.00"):
#             raise forms.ValidationError("Payment amount must be greater than 0.")
#         return amt
# """
# # # sales/forms.py
# from django import forms
# from decimal import Decimal
# from .models import Sale, SaleItem, CreditPayment
# from inventory.models import Product


# class SaleForm(forms.ModelForm):
#     amount_paid = forms.DecimalField(required=False, min_value=Decimal("0.00"))
#     due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

#     class Meta:
#         model = Sale
#         fields = ["customer_name", "customer_phone", "payment_method", "discount", "amount_paid", "due_date"]

#     def clean(self):
#         cleaned = super().clean()
#         pm = cleaned.get("payment_method")
#         amount_paid = cleaned.get("amount_paid") or Decimal("0.00")
#         due_date = cleaned.get("due_date")

#         if pm == "credit":
#             # due_date is recommended but optional—uncomment if client insists it must be set
#             # if not due_date:
#             #     self.add_error("due_date", "Due date is required for credit sales.")

#             if amount_paid < Decimal("0.00"):
#                 self.add_error("amount_paid", "Amount paid cannot be negative.")
#         else:
#             # if not credit, ignore these
#             cleaned["amount_paid"] = Decimal("0.00")
#             cleaned["due_date"] = None

#         return cleaned


# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "quantity", "unit_price"]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         self.fields["product"].widget.attrs.update({"class": "product-select"})
#         self.fields["quantity"].widget.attrs.update({"class": "qty-input"})
#         self.fields["unit_price"].widget.attrs.update({"class": "price-input", "readonly": "readonly"})

#         self.fields["product"].queryset = Product.objects.all()

#     def clean(self):
#         cleaned = super().clean()
#         product = cleaned.get("product")
#         qty = cleaned.get("quantity")

#         if product and qty and qty > product.quantity:
#             raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")
#         return cleaned


# class CreditPaymentForm(forms.ModelForm):
#     class Meta:
#         model = CreditPayment
#         fields = ["amount", "payment_method", "reference"]



# # sales/forms.py
# from django import forms
# from .models import Sale, SaleItem, CreditPayment
# from inventory.models import Product

# class SaleForm(forms.ModelForm):
#     # extra fields (not required)
#     amount_paid = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=12)
#     due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

#     class Meta:
#         model = Sale
#         fields = ["customer_name", "customer_phone", "payment_method", "discount", "amount_paid", "due_date"]

#     def clean(self):
#         cleaned = super().clean()
#         pm = cleaned.get("payment_method")
#         customer_name = cleaned.get("customer_name")
#         amount_paid = cleaned.get("amount_paid") or 0

#         # ✅ if credit, require customer name (you can also require phone)
#         if pm == "credit" and not customer_name:
#             raise forms.ValidationError("Customer name is required for credit sales.")

#         if amount_paid and amount_paid < 0:
#             raise forms.ValidationError("Amount paid cannot be negative.")
#         return cleaned


# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "quantity", "unit_price"]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         self.fields["product"].widget.attrs.update({
#             "class": "product-select w-full rounded-lg p-2"
#         })
#         self.fields["quantity"].widget.attrs.update({
#             "class": "qty-input w-full rounded-lg p-2"
#         })
#         self.fields["unit_price"].widget.attrs.update({
#             "class": "price-input w-full rounded-lg p-2",
#             "readonly": "readonly"
#         })

#         self.fields["product"].queryset = Product.objects.all()
#         self.fields["product"].label_from_instance = (
#             lambda obj: f"{obj.name} (Stock: {obj.quantity})"
#         )

#     def clean(self):
#         cleaned = super().clean()
#         product = cleaned.get("product")
#         qty = cleaned.get("quantity")
#         if product and qty and qty > product.quantity:
#             raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")
#         return cleaned


# class CreditPaymentForm(forms.ModelForm):
#     class Meta:
#         model = CreditPayment
#         fields = ["amount", "payment_method", "reference"]


# sales/forms.py
# from django import forms
# from .models import Sale, SaleItem
# from inventory.models import Product

# class SaleForm(forms.ModelForm):
#     class Meta:
#         model = Sale
#         fields = ["customer_name", "customer_phone", "payment_method", "discount"]

# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "quantity", "unit_price"]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         self.fields["product"].widget.attrs.update({
#             "class": "product-select w-full rounded-lg p-2"
#         })
#         self.fields["quantity"].widget.attrs.update({
#             "class": "qty-input w-full rounded-lg p-2"
#         })
#         self.fields["unit_price"].widget.attrs.update({
#             "class": "price-input w-full rounded-lg p-2",
#             "readonly": "readonly"
#         })

#         self.fields["product"].queryset = Product.objects.all()
#         self.fields["product"].label_from_instance = (
#             lambda obj: f"{obj.name} (Stock: {obj.quantity})"
#         )

#     def clean(self):
#         cleaned = super().clean()
#         product = cleaned.get("product")
#         qty = cleaned.get("quantity")

#         if product and qty and qty > product.quantity:
#             raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")

#         return cleaned

# from django import forms
# from .models import Sale, SaleItem
# from inventory.models import Product


# class SaleForm(forms.ModelForm):
#     class Meta:
#         model = Sale
#         fields = ["customer_name", "customer_phone", "payment_method", "discount"]


# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "quantity", "unit_price"]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         # Add CSS classes to fields (needed for the JS auto-calculation)
#         self.fields["product"].widget.attrs.update({
#             "class": "product-select w-full rounded-lg p-2"
#         })
#         self.fields["quantity"].widget.attrs.update({
#             "class": "qty-input w-full rounded-lg p-2"
#         })
#         self.fields["unit_price"].widget.attrs.update({
#             "class": "price-input w-full rounded-lg p-2",
#             "readonly": "readonly"   # user should NOT type price manually
#         })

#         # Show product name + stock remaining inside dropdown
#         self.fields["product"].queryset = Product.objects.all()
#         self.fields["product"].label_from_instance = (
#             lambda obj: f"{obj.name} (Stock: {obj.quantity})"
#         )

#     def clean(self):
#         cleaned = super().clean()
#         product = cleaned.get("product")
#         qty = cleaned.get("quantity")

#         # Stock validation
#         if product and qty:
#             if qty > product.quantity:
#                 raise forms.ValidationError(
#                     f"Not enough stock! Available: {product.quantity}"
#                 )
#         return cleaned


# from django import forms
# from .models import Sale, SaleItem
# from inventory.models import Product

# class SaleForm(forms.ModelForm):
#     class Meta:
#         model = Sale

#         fields = ["customer_name", "payment_method", "customer_phone", "discount"]
#         # fields = ["note", "customer_name", "payment_method", "total_amount"] first version without note and it was removed later however for the first time it was only note
# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "quantity", "unit_price"]

#     def clean(self):
#         cleaned = super().clean()
#         product = cleaned.get("product")
#         qty = cleaned.get("quantity")

#         if product and qty:
#             if qty > product.quantity:
#                 raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")

#         return cleaned

# class SaleItemForm(forms.ModelForm):
#     class Meta:
#         model = SaleItem
#         fields = ["product", "quantity", "unit_price"]
