# inventory/services.py
from decimal import Decimal
from django.db import transaction

from .models import Product


def q2(value) -> Decimal:
    """Quantize to 2 decimal places."""
    return Decimal(value or "0.00").quantize(Decimal("0.01"))


@transaction.atomic
def receive_weight_boxes(*, product: Product, boxes_received: int, box_weight_kg: Decimal) -> Product:
    """
    Receive boxes for a weighted product.
    Updates Product fields only (no StockBox).
    """
    product = Product.objects.select_for_update().get(id=product.id)

    boxes_received = int(boxes_received or 0)
    bw = q2(box_weight_kg)

    if boxes_received <= 0:
        raise ValueError("boxes_received must be > 0")
    if bw <= 0:
        raise ValueError("box_weight_kg must be > 0")

    product.is_weighted = True
    product.track_method = "boxed_weight"
    product.box_weight_kg = bw

    product.boxes_in_stock = int(product.boxes_in_stock or 0) + boxes_received

    # If current remaining not initialized, initialize as full
    if q2(product.box_remaining_kg) <= 0 and product.boxes_in_stock > 0:
        product.box_remaining_kg = bw

    product.save(update_fields=[
        "is_weighted", "track_method", "box_weight_kg",
        "boxes_in_stock", "box_remaining_kg"
    ])
    return product


@transaction.atomic
def consume_weight(*, product: Product, kg_to_sell: Decimal) -> Product:
    """
    Deduct kg using Code B rule:
    - Deduct from current box (box_remaining_kg)
    - When it hits 0, decrement boxes_in_stock and move to next full box if any
    """
    product = Product.objects.select_for_update().get(id=product.id)

    if not product.is_weighted or product.track_method != "boxed_weight":
        raise ValueError("Product is not configured for boxed-weight sales.")

    bw = q2(product.box_weight_kg)
    if bw <= 0:
        raise ValueError("box_weight_kg is not set.")

    if int(product.boxes_in_stock or 0) <= 0:
        raise ValueError("No boxes in stock.")

    kg_left = q2(kg_to_sell)
    if kg_left <= 0:
        return product

    # init remaining if not set
    br = q2(product.box_remaining_kg)
    if br <= 0:
        br = bw
        product.box_remaining_kg = br

    # check available
    available = product.available_weight_kg()
    if kg_left > available:
        raise ValueError(f"Not enough kg in stock. Available: {available}kg")

    while kg_left > 0:
        br = q2(product.box_remaining_kg)

        # if current box empty, move to next box (decrement then refill)
        if br <= 0:
            product.boxes_in_stock -= 1
            if product.boxes_in_stock <= 0:
                product.boxes_in_stock = 0
                product.box_remaining_kg = Decimal("0.00")
                break
            product.box_remaining_kg = bw
            br = bw

        take = min(br, kg_left)
        product.box_remaining_kg = q2(br - take)
        kg_left = q2(kg_left - take)

        # if finished current box exactly, consume one box
        if q2(product.box_remaining_kg) == Decimal("0.00"):
            product.boxes_in_stock -= 1
            if product.boxes_in_stock > 0:
                product.box_remaining_kg = bw
            else:
                product.boxes_in_stock = 0
                product.box_remaining_kg = Decimal("0.00")
                break

    product.save(update_fields=["boxes_in_stock", "box_remaining_kg"])
    return product




# from decimal import Decimal
# from django.db import transaction
# from django.utils import timezone
# from django.db.models import Sum

# from .models import Product, StockBox, StockReceipt


# @transaction.atomic
# def sync_product_box_counters(product: Product):
#     """
#     Optional: keep Product.boxes_in_stock & Product.box_remaining_kg in sync for display.
#     StockBox remains the source of truth.
#     """
#     # Lock product row
#     product = Product.objects.select_for_update().get(id=product.id)

#     # How many boxes still have stock?
#     boxes_qs = (
#         StockBox.objects.select_for_update()
#         .filter(product=product, remaining_kg__gt=0)
#         .order_by("id")
#     )
#     count = boxes_qs.count()

#     first_box = boxes_qs.first()
#     product.boxes_in_stock = count
#     product.box_remaining_kg = first_box.remaining_kg if first_box else Decimal("0.00")

#     product.save(update_fields=["boxes_in_stock", "box_remaining_kg"])


# @transaction.atomic
# def consume_weight_from_boxes(product: Product, kg_to_consume: Decimal):
#     """
#     FIFO consume from StockBox rows (oldest first).
#     """
#     kg_to_consume = Decimal(kg_to_consume or 0).quantize(Decimal("0.01"))
#     if kg_to_consume <= 0:
#         return

#     product = Product.objects.select_for_update().get(id=product.id)
#     if not product.is_weighted:
#         raise ValueError("Product is not weighted.")

#     # total available from StockBox (source of truth)
#     total = (
#         StockBox.objects.select_for_update()
#         .filter(product=product, remaining_kg__gt=0)
#         .aggregate(s=Sum("remaining_kg"))["s"]
#     ) or Decimal("0.00")

#     total = Decimal(total).quantize(Decimal("0.01"))
#     if kg_to_consume > total:
#         raise ValueError(f"Not enough kg in stock. Available: {total}kg")

#     remaining = kg_to_consume

#     boxes = (
#         StockBox.objects.select_for_update()
#         .filter(product=product, remaining_kg__gt=0)
#         .order_by("id")
#     )

#     for box in boxes:
#         if remaining <= 0:
#             break

#         take = min(box.remaining_kg, remaining)
#         box.remaining_kg = (box.remaining_kg - take).quantize(Decimal("0.01"))

#         if box.remaining_kg <= 0:
#             box.remaining_kg = Decimal("0.00")
#             box.consumed_on = timezone.now()

#         box.save(update_fields=["remaining_kg", "consumed_on"])
#         remaining = (remaining - take).quantize(Decimal("0.01"))

#     # keep display counters synced (optional but nice)
#     sync_product_box_counters(product)


# @transaction.atomic
# def restock_product_boxes(product: Product, boxes_received: int, box_weight_kg: Decimal, received_by=None):
#     """
#     Restock by creating StockReceipt + StockBox rows.
#     """
#     boxes_received = int(boxes_received or 0)
#     box_weight_kg = Decimal(box_weight_kg or 0).quantize(Decimal("0.01"))

#     if boxes_received <= 0 or box_weight_kg <= 0:
#         return

#     product = Product.objects.select_for_update().get(id=product.id)
#     product.is_weighted = True
#     product.track_method = "boxed_weight"
#     product.box_weight_kg = box_weight_kg
#     product.save(update_fields=["is_weighted", "track_method", "box_weight_kg"])

#     receipt = StockReceipt.objects.create(
#         product=product,
#         boxes_received=boxes_received,
#         box_weight_kg=box_weight_kg,
#         received_by=received_by,
#     )

#     StockBox.objects.bulk_create([
#         StockBox(
#             receipt=receipt,
#             product=product,
#             capacity_kg=box_weight_kg,
#             remaining_kg=box_weight_kg,
#         )
#         for _ in range(boxes_received)
#     ])

#     sync_product_box_counters(product)




# # inventory/services.py
# from decimal import Decimal
# from django.db import transaction
# from django.utils import timezone

# from .models import (
#     Product,
#     StockBox,
#     SaleableWeightSize,
#     StockReceipt,
#     WeightSizeAllocation,
# )

# @transaction.atomic
# def ensure_default_sizes(product: Product):
#     """
#     Create default 5/10/20/30 sizes if missing (optional).
#     """
#     defaults = [Decimal("5"), Decimal("10"), Decimal("20"), Decimal("30")]
#     for s in defaults:
#         SaleableWeightSize.objects.get_or_create(
#             product=product,
#             size_kg=s,
#             defaults={"price": Decimal("0.00")},
#         )

#     for size in product.weight_sizes.all():
#         WeightSizeAllocation.objects.get_or_create(size=size)


# @transaction.atomic
# def get_next_available_box(product: Product):
#     return (
#         StockBox.objects
#         .select_for_update()
#         .filter(product=product, remaining_kg__gt=0)
#         .order_by("id")
#         .first()
#     )


# @transaction.atomic
# def consume_weight_from_boxes(product: Product, size_kg: Decimal, qty_units: int):
#     """
#     Consume total_kg = size_kg * qty_units from StockBox.
#     """
#     total_to_consume = (Decimal(size_kg) * Decimal(qty_units)).quantize(Decimal("0.01"))
#     if total_to_consume <= 0:
#         return

#     size = SaleableWeightSize.objects.select_for_update().get(product=product, size_kg=size_kg)
#     alloc, _ = WeightSizeAllocation.objects.select_for_update().get_or_create(size=size)

#     if not alloc.current_box or alloc.current_box.remaining_kg <= 0:
#         alloc.current_box = get_next_available_box(product)
#         alloc.save(update_fields=["current_box"])

#     while total_to_consume > 0:
#         box = alloc.current_box
#         if not box:
#             raise ValueError(
#                 f"Not enough stock for {product.name}. Needed {total_to_consume}kg more."
#             )

#         box = StockBox.objects.select_for_update().get(id=box.id)

#         if box.remaining_kg <= 0:
#             alloc.current_box = get_next_available_box(product)
#             alloc.save(update_fields=["current_box"])
#             continue

#         take = min(box.remaining_kg, total_to_consume)
#         box.remaining_kg = (box.remaining_kg - take).quantize(Decimal("0.01"))

#         if box.remaining_kg <= 0:
#             box.remaining_kg = Decimal("0.00")
#             box.consumed_on = timezone.now()

#         box.save(update_fields=["remaining_kg", "consumed_on"])

#         total_to_consume = (total_to_consume - take).quantize(Decimal("0.01"))

#         if total_to_consume > 0:
#             alloc.current_box = get_next_available_box(product)
#             alloc.save(update_fields=["current_box"])


# @transaction.atomic
# def restock_product(product: Product, boxes_info: list[dict], received_by=None):
#     """
#     Restock product with given boxes_info.
#     boxes_info: [{'boxes_received': 10, 'box_weight_kg': 30.0}, ...]
#     """
#     for info in boxes_info:
#         boxes_received = int(info.get("boxes_received", 0))
#         box_weight_kg = Decimal(str(info.get("box_weight_kg", "0.00"))).quantize(Decimal("0.01"))

#         if boxes_received <= 0 or box_weight_kg <= 0:
#             continue

#         receipt = StockReceipt.objects.create(
#             product=product,
#             boxes_received=boxes_received,
#             box_weight_kg=box_weight_kg,
#             received_by=received_by,
#         )

#         StockBox.objects.bulk_create([
#             StockBox(
#                 receipt=receipt,
#                 product=product,
#                 capacity_kg=box_weight_kg,
#                 remaining_kg=box_weight_kg,
#             )
#             for _ in range(boxes_received)
#         ])



# # inventory/services.py
# from decimal import Decimal
# from django.db import transaction
# from django.utils import timezone
# from .models import Product, StockBox, SaleableWeightSize, StockReceipt, WeightSizeAllocation

# # deduction logic (NEW file)

# @transaction.atomic
# def ensure_default_sizes(product: Product):
#     """
#     # Create default 5/10/20/30 sizes if missing (optional).
# """
#     defaults = [Decimal("5"), Decimal("10"), Decimal("20"), Decimal("30")]
#     for s in defaults:
#         SaleableWeightSize.objects.get_or_create(product=product, size_kg=s, defaults={"price": Decimal("0.00")})
#     for size in product.weight_sizes.all():
#         WeightSizeAllocation.objects.get_or_create(size=size)


# @transaction.atomic
# def get_next_available_box(product: Product):
#     return (
#         StockBox.objects
#         .select_for_update()
#         .filter(product=product, remaining_kg__gt=0)
#         .order_by("id")
#         .first()
#     )


# @transaction.atomic
# def consume_weight_from_boxes(product: Product, size_kg: Decimal, qty_units: int):
#     """
#     # Consume total_kg = size_kg * qty_units from StockBox.
#     # Start from allocation.current_box; if it finishes, continue with next boxes.
# """
#     total_to_consume = (Decimal(size_kg) * Decimal(qty_units)).quantize(Decimal("0.01"))

#     if total_to_consume <= 0:
#         return

#     size = SaleableWeightSize.objects.select_for_update().get(product=product, size_kg=size_kg)
#     alloc, _ = WeightSizeAllocation.objects.select_for_update().get_or_create(size=size)

#     # pick current box if missing/consumed
#     if not alloc.current_box or alloc.current_box.remaining_kg <= 0:
#         alloc.current_box = get_next_available_box(product)
#         alloc.save(update_fields=["current_box"])

#     while total_to_consume > 0:
#         box = alloc.current_box
#         if not box:
#             raise ValueError(f"Not enough stock for {product.name}. Needed {total_to_consume}kg more.")

#         box = StockBox.objects.select_for_update().get(id=box.id)

#         if box.remaining_kg <= 0:
#             # move to next
#             alloc.current_box = get_next_available_box(product)
#             alloc.save(update_fields=["current_box"])
#             continue

#         take = min(box.remaining_kg, total_to_consume)
#         box.remaining_kg = (box.remaining_kg - take).quantize(Decimal("0.01"))

#         if box.remaining_kg <= 0:
#             box.remaining_kg = Decimal("0.00")
#             box.consumed_on = timezone.now()

#         box.save(update_fields=["remaining_kg", "consumed_on"])

#         total_to_consume = (total_to_consume - take).quantize(Decimal("0.01"))

#         if total_to_consume > 0:
#             alloc.current_box = get_next_available_box(product)
#             alloc.save(update_fields=["current_box"])
#             continue     #all are not chatGpt codes
# @transaction.atomic
# def restock_product(product: Product, boxes_info: list[dict], received_by=None):
#     """
#     # Restock product with given boxes_info.
#     # boxes_info: list of dicts with keys 'boxes_received' and 'box_weight_kg'.
#     # Example: [{'boxes_received': 10, 'box_weight_kg': 30.0}, ...]
# """
#     for info in boxes_info:
#         boxes_received = info.get('boxes_received', 0)
#         box_weight_kg = Decimal(info.get('box_weight_kg', '0.00')).quantize(Decimal("0.01"))

#         if boxes_received <= 0 or box_weight_kg <= 0:
#             continue

#         receipt = StockReceipt.objects.create(
#             product=product,
#             boxes_received=boxes_received,
#             box_weight_kg=box_weight_kg,
#             received_by=received_by
#         )

#         # Create StockBox entries
#         stock_boxes = [
#             StockBox(
#                 receipt=receipt,
#                 product=product,
#                 capacity_kg=box_weight_kg,
#                 remaining_kg=box_weight_kg
#             )
#             for _ in range(boxes_received)
#         ]
#         StockBox.objects.bulk_create(stock_boxes)
        
