# sales/forms.py
from decimal import Decimal
from django import forms
from .models import Sale, SaleItem, CreditPayment
from inventory.models import Product


class SaleForm(forms.ModelForm):
    # Only used when payment_method == "credit"
    amount_paid = forms.DecimalField(required=False, min_value=Decimal("0.00"))
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    apply_vat = forms.BooleanField(required=False, initial=False)  # ✅ NEW

    class Meta:
        model = Sale
        fields = ["customer_name", "customer_phone", "payment_method", "discount", "apply_vat", "amount_paid", "due_date"]

    def clean(self):
        cleaned = super().clean()
        pm = cleaned.get("payment_method")
        
        cleaned["apply_vat"] = bool(cleaned.get("apply_vat"))
        amount_paid = cleaned.get("amount_paid") or Decimal("0.00")
        due_date = cleaned.get("due_date")
         # ✅ ensure apply_vat becomes True/False cleanly

        if pm == "credit":
            # optional required due date (enable if client insists)
            # if not due_date:
            #     self.add_error("due_date", "Due date is required for credit sales.")
            if amount_paid < Decimal("0.00"):
                self.add_error("amount_paid", "Amount paid cannot be negative.")
        else:
            # not credit -> ignore these
            cleaned["amount_paid"] = Decimal("0.00")
            cleaned["due_date"] = None

        return cleaned


class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ["product", "quantity", "unit_price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["product"].widget.attrs.update({"class": "product-select"})
        self.fields["quantity"].widget.attrs.update({"class": "qty-input"})
        self.fields["unit_price"].widget.attrs.update({"class": "price-input", "readonly": "readonly"})

        self.fields["product"].queryset = Product.objects.all()

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        qty = cleaned.get("quantity")

        if product and qty and qty > product.quantity:
            raise forms.ValidationError(f"Not enough stock! Available: {product.quantity}")
        return cleaned


class CreditPaymentForm(forms.ModelForm):
    class Meta:
        model = CreditPayment
        fields = ["amount", "payment_method", "reference"]

    def clean_amount(self):
        amt = self.cleaned_data.get("amount") or Decimal("0.00")
        if amt <= Decimal("0.00"):
            raise forms.ValidationError("Payment amount must be greater than 0.")
        return amt

# # sales/forms.py
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
