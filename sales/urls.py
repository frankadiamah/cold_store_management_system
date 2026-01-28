
# sales/urls.py
from django.urls import path
from . import views

# app_name = "sales"

urlpatterns = [
    path("create/", views.create_sale, name="create_sale"),
    path("sales/", views.sale_list, name="sale_list"),
    path("credits/", views.credit_sales_list, name="credit_sales_list"),
    path("credits/<int:sale_id>/pay/", views.credit_payment_add, name="credit_payment_add"),
    path("sales/receipt/<int:sale_id>/", views.sale_receipt, name="sale_receipt"),
    path("receipt/<int:sale_id>/", views.receipt_view, name="receipt_view"),
    path("sales/retail/", views.retail_sales_list, name="retail_sales_list"),
    path("sales/wholesale/", views.wholesale_sales_list, name="wholesale_sales_list")
]


# from django.urls import path
# from . import views

# urlpatterns = [
#     path("create/", views.create_sale, name="create_sale"),
#     path("", views.sale_list, name="sale_list"),

#     path("credits/", views.credit_sales_list, name="credit_sales_list"),
#     path("credits/<int:sale_id>/pay/", views.credit_payment_add, name="credit_payment_add"),

#     path("receipt/<int:sale_id>/", views.sale_receipt, name="sale_receipt"),
#     path("receipt/pdf/<int:sale_id>/", views.receipt_view, name="receipt_view"),
# ]