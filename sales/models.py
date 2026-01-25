# sales/models.py
from django.db import models
from django.contrib.auth.models import User
from inventory.models import Product, ProductWeightPrice
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum


# class ProductWeightPrice(models.Model):
#     """
#     Defines weight sizes & prices for weighted products (Fish, Salmon, etc.)
#     Example: 5kg, 10kg, 20kg...
#     """
#     product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="weight_prices")
#     weight_kg = models.DecimalField(max_digits=10, decimal_places=2)  # e.g. 5, 10, 20, 30
#     retail_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     is_active = models.BooleanField(default=True)

#     class Meta:
#         ordering = ["weight_kg"]
#         unique_together = ("product", "weight_kg")

#     def __str__(self):
#         return f"{self.product.name} - {self.weight_kg}kg"


class Sale(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('momo', 'Mobile Money'),
        ('card', 'Card'),
        ('credit', 'Credit (Pay Later)'),
    ]

    SALE_TYPES = [
        ("retail", "Retail"),
        ("wholesale", "Wholesale"),
    ]

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    sale_type = models.CharField(max_length=20, choices=SALE_TYPES, default="retail")

    customer_name = models.CharField(max_length=100, blank=True, null=True)
    customer_phone = models.CharField(max_length=15, blank=True, null=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')

    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # ✅ VAT optional
    apply_vat = models.BooleanField(default=False)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.04"))  # 4%

    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # ✅ CREDIT
    is_credit = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    due_date = models.DateField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    @property
    def balance_due_calc(self):
        return max(Decimal("0.00"), (self.total_amount or Decimal("0.00")) - (self.amount_paid or Decimal("0.00")))

    @property
    def is_paid(self):
        return self.balance_due_calc <= Decimal("0.00")

    def recalc_credit(self, save=False):
        total_paid = self.credit_payments.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        self.amount_paid = Decimal(total_paid)

        if self.is_credit and self.is_paid:
            self.is_credit = False

        if save:
            self.save(update_fields=["amount_paid", "is_credit"])

    def __str__(self):
        tag = "CREDIT" if self.is_credit and not self.is_paid else "PAID"
        return f"{self.get_sale_type_display()} Sale #{self.id} ({tag}) - ₵{self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)

    # ✅ weight size selected (e.g. 5kg, 10kg, 30kg)
    weight_price = models.ForeignKey(ProductWeightPrice, on_delete=models.SET_NULL, null=True, blank=True)

    quantity = models.PositiveIntegerField(default=1)  # number of “packs” of the selected weight
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))  # price of that weight
    
    
    def sold_weight_kg(self):
        if self.weight_price:
            return Decimal(self.quantity or 0) * Decimal(self.weight_price.weight_kg or Decimal("0.00"))
        return Decimal("0.00")

    def line_total(self):
        return Decimal(self.quantity or 0) * Decimal(self.unit_price or Decimal("0.00"))

    def __str__(self):
        pname = self.product.name if self.product else "Deleted Product"
        if self.weight_price:
            return f"{pname} {self.weight_price.weight_kg}kg x {self.quantity}"
        return f"{pname} x {self.quantity}"
    # def weight_kg(self):
    #     return self.weight_price.weight_kg if self.weight_price else Decimal("0.00")

    # def total_kg(self):
    #     return (self.weight_kg() * Decimal(self.quantity)).quantize(Decimal("0.01"))

    # def line_total(self):
    #     return (Decimal(self.quantity) * (self.unit_price or Decimal("0.00"))).quantize(Decimal("0.01"))

    # def __str__(self):
    #     pname = self.product.name if self.product else "Deleted Product"
    #     w = self.weight_kg()
    #     return f"{pname} ({w}kg) x {self.quantity}"


class CreditPayment(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="credit_payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField(
        max_length=20,
        choices=[("cash", "Cash"), ("momo", "Mobile Money"), ("card", "Card")],
        default="cash"
    )
    reference = models.CharField(max_length=80, blank=True)
    paid_on = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-paid_on"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sale.recalc_credit(save=True)

    def __str__(self):
        return f"Payment ₵{self.amount} for Sale #{self.sale_id}"





"""# sales/models.py
from django.db import models
from django.contrib.auth.models import User
from inventory.models import Product, SaleableWeightSize
from decimal import Decimal
from django.utils import timezone

VAT_RATE = Decimal("0.15")


class Sale(models.Model):
    PAYMENT_METHODS = [
        ("cash", "Cash"),
        ("momo", "Mobile Money"),
        ("card", "Card"),
        ("credit", "Credit (Pay Later)"),
    ]

    SALE_TYPES = [
        ("retail", "Retail"),
        ("wholesale", "Wholesale"),
    ]

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    sale_type = models.CharField(max_length=20, choices=SALE_TYPES, default="retail")

    customer_name = models.CharField(max_length=100, blank=True, null=True)
    customer_phone = models.CharField(max_length=15, blank=True, null=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="cash")

    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # ✅ Optional VAT
    apply_vat = models.BooleanField(default=True)

    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # CREDIT
    is_credit = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    due_date = models.DateField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    @property
    def balance_due_calc(self):
        return max(
            Decimal("0.00"),
            (self.total_amount or Decimal("0.00")) - (self.amount_paid or Decimal("0.00"))
        )

    @property
    def is_paid(self):
        return self.balance_due_calc <= Decimal("0.00")

    def recalc_credit(self, save=False):
        total_paid = self.credit_payments.aggregate(s=models.Sum("amount"))["s"] or Decimal("0.00")
        self.amount_paid = Decimal(total_paid)

        if self.is_credit and self.is_paid:
            self.is_credit = False

        if save:
            self.save(update_fields=["amount_paid", "is_credit"])

    def __str__(self):
        tag = "CREDIT" if self.is_credit and not self.is_paid else "PAID"
        return f"{self.get_sale_type_display()} Sale #{self.id} ({tag}) - ₵{self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)

    # ✅ only used for boxed_weight products
    weight_size = models.ForeignKey(SaleableWeightSize, on_delete=models.SET_NULL, null=True, blank=True)

    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def line_total(self):
        qty = self.quantity or 0
        price = self.unit_price or Decimal("0.00")
        return Decimal(qty) * Decimal(price)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and self.product:
            # ✅ boxed weight products deduct from boxes
            if getattr(self.product, "track_method", "unit") == "boxed_weight":
                from inventory.services import consume_weight_from_boxes

                if not self.weight_size:
                    raise ValueError("Weight size is required for boxed-weight product sales.")

                consume_weight_from_boxes(
                    product=self.product,
                    size_kg=self.weight_size.size_kg,
                    qty_units=self.quantity
                )

            else:
                # ✅ unit products deduct quantity
                self.product.quantity = max(0, self.product.quantity - self.quantity)
                self.product.save()

    def __str__(self):
        pname = self.product.name if self.product else "Deleted Product"
        if self.weight_size:
            return f"{pname} {self.weight_size.size_kg}kg x {self.quantity}"
        return f"{pname} x {self.quantity} @ {self.unit_price}"


class CreditPayment(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="credit_payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField(
        max_length=20,
        choices=[("cash", "Cash"), ("momo", "Mobile Money"), ("card", "Card")],
        default="cash"
    )
    reference = models.CharField(max_length=80, blank=True)
    paid_on = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-paid_on"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sale.recalc_credit(save=True)

    def __str__(self):
        return f"Payment ₵{self.amount} for Sale #{self.sale_id}"
"""




"""# sales/models.py
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Sum
from inventory.models import Product


class Sale(models.Model):
    PAYMENT_METHODS = [
        ("cash", "Cash"),
        ("momo", "Mobile Money"),
        ("card", "Card"),
        ("credit", "Credit (Pay Later)"),
    ]

    SALE_TYPES = [
        ("retail", "Retail"),
        ("wholesale", "Wholesale"),
    ]

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    sale_type = models.CharField(max_length=20, choices=SALE_TYPES, default="retail")

    customer_name = models.CharField(max_length=100, blank=True, null=True)
    customer_phone = models.CharField(max_length=15, blank=True, null=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="cash")

    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    apply_vat = models.BooleanField(default=True)  # ✅ NEW
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # CREDIT
    is_credit = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    due_date = models.DateField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    @property
    def balance_due_calc(self) -> Decimal:
        return max(
            Decimal("0.00"),
            (self.total_amount or Decimal("0.00")) - (self.amount_paid or Decimal("0.00"))
        )

    @property
    def is_paid(self) -> bool:
        return self.balance_due_calc <= Decimal("0.00")

    def recalc_credit(self, save=False):
        ""
        Sync Sale.amount_paid from CreditPayment rows.
        ""
        total_paid = self.credit_payments.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        self.amount_paid = Decimal(total_paid)

        # auto mark non-credit if fully paid
        if self.is_credit and self.is_paid:
            self.is_credit = False

        if save:
            self.save(update_fields=["amount_paid", "is_credit"])

    def __str__(self):
        tag = "CREDIT" if self.is_credit and not self.is_paid else "PAID"
        return f"{self.get_sale_type_display()} Sale #{self.id} ({tag}) - ₵{self.total_amount}"


# class SaleItem(models.Model):
#     sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
#     product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
#     quantity = models.IntegerField()
#     unit_price = models.DecimalField(max_digits=10, decimal_places=2)

#     def line_total(self):
#         return Decimal(self.quantity or 0) * Decimal(self.unit_price or Decimal("0.00"))
    
#     @property
#     def line_total_amount(self):
#         return self.line_total()

#     def save(self, *args, **kwargs):
#         super().save(*args, **kwargs)
#         # adjust inventory only
#         if self.product:
#             self.product.quantity = max(0, self.product.quantity - (self.quantity or 0))
#             self.product.save(update_fields=["quantity"])

#     def __str__(self):
#         pname = self.product.name if self.product else "Deleted Product"
#         return f"{pname} x {self.quantity} @ {self.unit_price}"


from inventory.models import Product, SaleableWeightSize
from inventory.services import consume_weight_from_boxes

class SaleItem(models.Model):
    sale = models.ForeignKey("Sale", on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)

    # ✅ new fields for weight products
    weight_size = models.ForeignKey(SaleableWeightSize, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def line_total(self):
        return Decimal(self.quantity or 0) * Decimal(self.unit_price or Decimal("0.00"))

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # ✅ Only adjust inventory once when created
        if is_new and self.product:
            if self.product.track_method == "boxed_weight":
                if not self.weight_size:
                    raise ValueError("Weight size is required for boxed_weight product.")
                consume_weight_from_boxes(
                    product=self.product,
                    size_kg=self.weight_size.size_kg,
                    qty_units=self.quantity
                )
            else:
                # old behavior (unit products)
                self.product.quantity = max(0, self.product.quantity - self.quantity)
                self.product.save()

class CreditPayment(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="credit_payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField(
        max_length=20,
        choices=[("cash", "Cash"), ("momo", "Mobile Money"), ("card", "Card")],
        default="cash"
    )
    reference = models.CharField(max_length=80, blank=True)
    paid_on = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-paid_on"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # keep Sale.amount_paid synced
        self.sale.recalc_credit(save=True)

    def __str__(self):
        return f"Payment ₵{self.amount} for Sale #{self.sale_id}"
""" 


#  # sales/models.py
# from django.db import models
# from django.contrib.auth.models import User
# from inventory.models import Product
# from decimal import Decimal
# from django.utils import timezone

# class Sale(models.Model):
#     PAYMENT_METHODS = [
#         ('cash', 'Cash'),
#         ('momo', 'Mobile Money'),
#         ('card', 'Card'),
#         ('credit', 'Credit (Pay Later)'),
#     ]

#     SALE_TYPES = [
#         ("retail", "Retail"),
#         ("wholesale", "Wholesale"),
#     ]

#     created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
#     sale_type = models.CharField(max_length=20, choices=SALE_TYPES, default="retail")

#     customer_name = models.CharField(max_length=100, blank=True, null=True)
#     customer_phone = models.CharField(max_length=15, blank=True, null=True)
#     payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')

#     discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
#     subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

#     # CREDIT
#     is_credit = models.BooleanField(default=False)
#     amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))  # ✅ add back
#     due_date = models.DateField(null=True, blank=True)
#     timestamp = models.DateTimeField(auto_now_add=True)

    
    
#     @property
#     def balance_due_calc(self):
#         return max(
#             Decimal("0.00"),
#             (self.total_amount or Decimal("0.00")) - (self.amount_paid or Decimal("0.00"))
#         )
    
#     @property
#     def is_paid(self):
#         return self.balance_due_calc <= Decimal("0.00")

#     def recalc_credit(self, save=False):
#         """
#         Keep amount_paid synced with CreditPayment records.
#         """
#         total_paid = self.credit_payments.aggregate(s=models.Sum("amount"))["s"] or Decimal("0.00")
#         self.amount_paid = Decimal(total_paid)

#         # auto flip credit off when fully paid
#         if self.is_credit and self.is_paid:
#             self.is_credit = False

#         if save:
#             self.save(update_fields=["amount_paid", "is_credit"])

#     def __str__(self):
#         tag = "CREDIT" if self.is_credit and not self.is_paid else "PAID"
#         return f"{self.get_sale_type_display()} Sale #{self.id} ({tag}) - ₵{self.total_amount}"


# class SaleItem(models.Model):
#     sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
#     product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
#     quantity = models.IntegerField()
#     unit_price = models.DecimalField(max_digits=10, decimal_places=2)

#     def line_total(self):
#         qty = self.quantity or 0
#         price = self.unit_price or Decimal("0.00")
#         return Decimal(qty) * Decimal(price)

#     def save(self, *args, **kwargs):
#         super().save(*args, **kwargs)
#         if self.product:
#             self.product.quantity = max(0, self.product.quantity - self.quantity)
#             self.product.save()

#     def __str__(self):
#         pname = self.product.name if self.product else "Deleted Product"
#         return f"{pname} x {self.quantity} @ {self.unit_price}"


# class CreditPayment(models.Model):
#     sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="credit_payments")
#     amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     payment_method = models.CharField(
#         max_length=20,
#         choices=[("cash", "Cash"), ("momo", "Mobile Money"), ("card", "Card")],
#         default="cash"
#     )
#     reference = models.CharField(max_length=80, blank=True)
#     paid_on = models.DateTimeField(default=timezone.now)
#     received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

#     class Meta:
#         ordering = ["-paid_on"]

#     def save(self, *args, **kwargs):
#         super().save(*args, **kwargs)
#         # keep Sale.amount_paid synced
#         self.sale.recalc_credit(save=True)

#     def __str__(self):
#         return f"Payment ₵{self.amount} for Sale #{self.sale_id}"


# # sales/models.py
# from django.db import models
# from django.contrib.auth.models import User
# from inventory.models import Product
# from decimal import Decimal
# from django.utils import timezone

# class Sale(models.Model):
#     PAYMENT_METHODS = [
#         ('cash', 'Cash'),
#         ('momo', 'Mobile Money'),
#         ('card', 'Card'),
#         ('credit', 'Credit (Pay Later)'),  # ✅ NEW
#     ]

#     SALE_TYPES = [
#         ("retail", "Retail"),
#         ("wholesale", "Wholesale"),
#     ]

#     created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
#     sale_type = models.CharField(max_length=20, choices=SALE_TYPES, default="retail")

#     customer_name = models.CharField(max_length=100, blank=True, null=True)
#     customer_phone = models.CharField(max_length=15, blank=True, null=True)
#     payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')

#     discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

#     subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

#     # ✅ CREDIT TRACKING
#     is_credit = models.BooleanField(default=False)
#     amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     due_date = models.DateField(null=True, blank=True)

#     timestamp = models.DateTimeField(auto_now_add=True)

#     @property
#     def is_paid(self):
        
#         return self.balance_due <= Decimal("0.00")
#     # this added by me just now due to intergrity error
#     # @property
#     # def balance_due(self):
#     #     return max(Decimal("0.00"), (self.total_amount or Decimal("0.00")) - (self.amount_paid or Decimal("0.00")))
    
#     def __str__(self):
#         tag = "CREDIT" if self.is_credit else "PAID"
#         return f"{self.get_sale_type_display()} Sale #{self.id} ({tag}) - ₵{self.total_amount}"


# class SaleItem(models.Model):
#     sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
#     product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
#     quantity = models.IntegerField()
#     unit_price = models.DecimalField(max_digits=10, decimal_places=2)

#     def line_total(self):
#         qty = self.quantity or 0
#         price = self.unit_price or Decimal("0.00")
#         return Decimal(qty) * Decimal(price)

#     def save(self, *args, **kwargs):
#         super().save(*args, **kwargs)

#         # ✅ Only adjust inventory here
#         if self.product:
#             self.product.quantity = max(0, self.product.quantity - self.quantity)
#             self.product.save()

#     def __str__(self):
#         pname = self.product.name if self.product else "Deleted Product"
#         return f"{pname} x {self.quantity} @ {self.unit_price}"


# # ✅ NEW: payments against credit sales
# class CreditPayment(models.Model):
#     sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="credit_payments")
#     amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     payment_method = models.CharField(
#         max_length=20,
#         choices=[("cash", "Cash"), ("momo", "Mobile Money"), ("card", "Card")],
#         default="cash"
#     )
#     reference = models.CharField(max_length=80, blank=True)
#     paid_on = models.DateTimeField(default=timezone.now)
#     received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

#     class Meta:
#         ordering = ["-paid_on"]

#     def __str__(self):
#         return f"Payment ₵{self.amount} for Sale #{self.sale_id}"



# # sales/models.py
# from django.db import models
# from django.contrib.auth.models import User
# from inventory.models import Product
# from decimal import Decimal

# class Sale(models.Model):
#     PAYMENT_METHODS = [
#         ('cash', 'Cash'),
#         ('momo', 'Mobile Money'),
#         ('card', 'Card'),
#     ]

#     SALE_TYPES = [
#         ("retail", "Retail"),
#         ("wholesale", "Wholesale"),
#     ]

#     created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
#     sale_type = models.CharField(max_length=20, choices=SALE_TYPES, default="retail")  # ✅ NEW

#     customer_name = models.CharField(max_length=100, blank=True, null=True)
#     customer_phone = models.CharField(max_length=15, blank=True, null=True)
#     payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')

#     discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

#     subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))  # ✅ NEW
#     vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))       # ✅ NEW
#     total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))     # = GRAND TOTAL

#     note = models.TextField(blank=True)
#     timestamp = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.get_sale_type_display()} Sale #{self.id} - ₵{self.total_amount}"


# class SaleItem(models.Model):
#     sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
#     product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
#     quantity = models.IntegerField()
#     unit_price = models.DecimalField(max_digits=10, decimal_places=2)

#     def line_total(self):
#         qty = self.quantity or 0
#         price = self.unit_price or Decimal("0.00")
#         return Decimal(qty) * Decimal(price)

#     def save(self, *args, **kwargs):
#         super().save(*args, **kwargs)

#         # ✅ Only adjust inventory here (DO NOT update sale.total_amount here)
#         if self.product:
#             self.product.quantity = max(0, self.product.quantity - self.quantity)
#             self.product.save()
#          # update sale total after saving items
#         sale_total = sum(item.line_total() for item in self.sale.items.all())
#         self.sale.total_amount = sale_total
#         self.sale.save()
        
#     def __str__(self):
#         pname = self.product.name if self.product else "Deleted Product"
#         return f"{pname} x {self.quantity} @ {self.unit_price}"




# from django.db import models
# from django.contrib.auth.models import User
# from inventory.models import Product

# class Sale(models.Model):
#     PAYMENT_METHODS = [
#         ('cash', 'Cash'),
#         ('momo', 'Mobile Money'),
#         ('card', 'Card'),
#     ]

#     created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
#     customer_name = models.CharField(max_length=100, blank=True, null=True)
#     payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
#     customer_phone = models.CharField(max_length=15, blank=True, null=True)
#     discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
#     total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
#     note = models.TextField(blank=True)
#     timestamp = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"Sale #{self.id} - ₵{self.total_amount}"

# class SaleItem(models.Model):
#     sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
#     product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
#     quantity = models.IntegerField()
#     unit_price = models.DecimalField(max_digits=10, decimal_places=2)

#     def line_total(self):
#         qty = self.quantity or 0
#         price = self.unit_price or 0
#         return qty * price

#     def save(self, *args, **kwargs):
#         super().save(*args, **kwargs)

#         # decrease inventory
#         if self.product:
#             self.product.quantity = max(0, self.product.quantity - self.quantity)
#             self.product.save()

#         # update sale total after saving items
#         sale_total = sum(item.line_total() for item in self.sale.items.all())
#         self.sale.total_amount = sale_total
#         self.sale.save()

#     def __str__(self):
#         return f"{self.product.name if self.product else 'Deleted Product'} x {self.quantity} @ {self.unit_price}"


# class SaleItem(models.Model):
#     sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
#     product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
#     quantity = models.IntegerField()
#     unit_price = models.DecimalField(max_digits=10, decimal_places=2)

#     def line_total(self):
#         return self.quantity*self.unit_price

#     def save(self, *args, **kwargs):
#         super().save(*args, **kwargs)
#         # decrease inventory
#         if self.product:
#             self.product.quantity = max(0, self.product.quantity - self.quantity)
#             self.product.save()

#         # update sale total amount after each item save
#         sale_total = sum(item.line_total() for item in self.sale.items.all())
#         self.sale.total_amount = sale_total
#         self.sale.save()

#     def __str__(self):
#         return f"{self.product.name if self.product else 'Deleted Product'} x {self.quantity} @ {self.unit_price}"
