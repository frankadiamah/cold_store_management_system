from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='inventory_dashboard'),
    path('products/', views.ProductListView.as_view(), name='product_list'),
    path('products/add/', views.product_create, name='product_add'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path("receive-boxes/", views.receive_stock_boxes, name="receive_stock_boxes"),
    path('stock/in/', views.stock_in, name='stock_in'),
    path('stock/out/', views.stock_out, name='stock_out'),
    path('stock/in/<int:pk>/edit/', views.stock_entry_edit, name='stock_entry_edit'),
    path('stock/out/<int:pk>/edit/', views.stock_out_edit, name='stock_out_edit'),
    path("prices/retail/", views.retail_price_list, name="retail_price_list"),
    path("prices/wholesale/", views.wholesale_price_list, name="wholesale_price_list"),

]


# from django.urls import path
# from . import views

# urlpatterns = [
#     path("", views.dashboard, name="inventory_dashboard"),
#     path("products/", views.ProductListView.as_view(), name="product_list"),
#     path("products/add/", views.ProductCreateView.as_view(), name="product_add"),
#     path("stock/in/", views.stock_in, name="stock_in"),
#     path("stock/out/", views.stock_out, name="stock_out"),
# ]
