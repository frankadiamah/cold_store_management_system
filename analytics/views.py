from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from datetime import datetime, timedelta
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from sales.models import Sale
from expenses.models import Expense
from inventory.models import Product
from users.utils import has_any_group  

@login_required
@has_any_group("SuperAdmin", "SubAdmin", "Admin", "Accountant")
def analytics_dashboard(request):
    today = datetime.today()
    dates = [(today - timedelta(days=i)).date() for i in range(6, -1, -1)]

    # ✅ Admin/Accountant see all; others see only their own
    sales_qs = Sale.objects.all()
    expenses_qs = Expense.objects.all()  # adjust app/model name
    products_qs = Product.objects.all()

    # sales_qs = Sale.objects.all()
    # expenses_qs = Expense.objects.all()

    if not (request.user.groups.filter(name="Admin").exists() or request.user.groups.filter(name="Accountant").exists()):
        sales_qs = sales_qs.filter(created_by=request.user)
        expenses_qs = expenses_qs.filter(created_by=request.user)
        products_qs = products_qs.filter(created_by=request.user)

    sales_data, expense_data, profit_data = [], [], []
    credit_sales_data, credit_outstanding_data = [], []

    for d in dates:
        sales_total = sales_qs.filter(timestamp__date=d).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        expenses_total = expenses_qs.filter(timestamp__date=d).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        credit_sales_total = sales_qs.filter(timestamp__date=d, is_credit=True).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        credit_outstanding = sales_qs.filter(timestamp__date=d, is_credit=True).aggregate(total=Sum(ExpressionWrapper(F("total_amount") - F("amount_paid"), output_field=DecimalField()))) ["total"] or Decimal("0.00")

        profit = sales_total - expenses_total

        sales_data.append(float(sales_total))
        expense_data.append(float(expenses_total))
        profit_data.append(float(profit))
        credit_sales_data.append(float(credit_sales_total))
        credit_outstanding_data.append(float(credit_outstanding))

    total_sales = sum(sales_data)
    total_expenses = sum(expense_data)
    total_profit = total_sales - total_expenses

    # ✅ Overall credit metrics for the period
    period_credit_sales = sales_qs.filter(is_credit=True, timestamp__date__in=dates).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    period_credit_outstanding = sales_qs.filter(is_credit=True, timestamp__date__in=dates).aggregate(total=Sum(ExpressionWrapper(F("total_amount") - F("amount_paid"), output_field=DecimalField()))) ["total"] or Decimal("0.00")

    top_products = products_qs.order_by("-quantity")[:5]

    context = {
        "dates": [d.strftime("%b %d") for d in dates],
        "sales_data": sales_data,
        "expense_data": expense_data,
        "profit_data": profit_data,

        # ✅ credit series
        "credit_sales_data": credit_sales_data,
        "credit_outstanding_data": credit_outstanding_data,

        # totals
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "total_profit": total_profit,

        # ✅ summary
        "period_credit_sales": float(period_credit_sales),
        "period_credit_outstanding": float(period_credit_outstanding),

        "top_products": top_products,
    }
    return render(request, "analytics/dashboard.html", context)



# def analytics_dashboard(request):
#     sales_qs = visible_qs(Sale.objects.all(), request.user)
#     expenses_qs = visible_qs(Expense.objects.all(), request.user)  # adjust app/model name

#     total_sales = sales_qs.aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
#     total_expenses = expenses_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
#     total_profit = total_sales - total_expenses

#     return render(request, "analytics/dashboard.html", {
#         "total_sales": total_sales,
#         "total_expenses": total_expenses,
#         "total_profit": total_profit,
#         # plus your chart lists computed from sales_qs/expenses_qs
#     })


# from django.shortcuts import render
# from django.contrib.auth.decorators import login_required
# from sales.models import Sale
# from expenses.models import Expense
# from inventory.models import Product
# from django.db.models import Sum
# from datetime import datetime, timedelta

# @login_required
# def analytics_dashboard(request):
#     # Sales & Expenses - last 7 days
#     today = datetime.today()
#     dates = [(today - timedelta(days=i)).date() for i in range(6, -1, -1)]

#     sales_data = []
#     expense_data = []
#     profit_data = []

#     for date in dates:
#         sales_total = Sale.objects.filter(timestamp__date=date, created_by=request.user).aggregate(total=Sum('total_amount'))['total'] or 0
#         expenses_total = Expense.objects.filter(timestamp__date=date, created_by=request.user).aggregate(total=Sum('amount'))['total'] or 0
#         profit = sales_total - expenses_total

#         sales_data.append(float(sales_total))
#         expense_data.append(float(expenses_total))
#         profit_data.append(float(profit))

#     # Summary totals
#     total_sales = sum(sales_data)
#     total_expenses = sum(expense_data)
#     total_profit = total_sales - total_expenses

#     # Top 5 best-selling products
#     top_products = (
#         Product.objects.filter(created_by=request.user)
#         .order_by('-quantity')[:5]
#     )

#     context = {
#         "dates": [d.strftime("%b %d") for d in dates],
#         "sales_data": sales_data,
#         "expense_data": expense_data,
#         "profit_data": profit_data,
#         "total_sales": total_sales,
#         "total_expenses": total_expenses,
#         "total_profit": total_profit,
#         "top_products": top_products,
#     }
#     return render(request, "analytics/dashboard.html", context)


#  currently replaced by analytics/views.py with different approach
# 
# 
# from django.shortcuts import render
# from django.contrib.auth.decorators import login_required
# from django.db.models import Sum
# from datetime import datetime, timedelta

# from sales.models import Sale
# from expenses.models import Expense
# from inventory.models import Product

# @login_required
# def analytics_dashboard(request):
#     today = datetime.today()
#     dates = [(today - timedelta(days=i)).date() for i in range(6, -1, -1)]

#     sales_data, expense_data, profit_data = [], [], []

#     for date in dates:
#         sales_total = (
#             Sale.objects
#             .filter(timestamp__date=date, created_by=request.user)
#             .aggregate(total=Sum("total_amount"))["total"] or 0
#         )
#         expenses_total = (
#             Expense.objects
#             .filter(timestamp__date=date, created_by=request.user)
#             .aggregate(total=Sum("amount"))["total"] or 0
#         )
#         profit = sales_total - expenses_total

#         sales_data.append(float(sales_total))
#         expense_data.append(float(expenses_total))
#         profit_data.append(float(profit))

#     total_sales = sum(sales_data)
#     total_expenses = sum(expense_data)
#     total_profit = total_sales - total_expenses

#     top_products = (
#         Product.objects.filter(created_by=request.user)
#         .order_by("-quantity")[:5]
#     )

#     context = {
#         "dates": [d.strftime("%b %d") for d in dates],
#         "sales_data": sales_data,
#         "expense_data": expense_data,
#         "profit_data": profit_data,
#         "total_sales": total_sales,
#         "total_expenses": total_expenses,
#         "total_profit": total_profit,
#         "top_products": top_products,
#     }
#     return render(request, "analytics/dashboard.html", context)








# to  to study and implement more advanced analytics features later
# @login_required
# def analytics_overview(request):
#     # Aggregate totals
#     total_sales = Sale.objects.filter(created_by=request.user).aggregate(total=Sum('total_amount'))['total'] or 0
#     total_expenses = Expense.objects.filter(created_by=request.user).aggregate(total=Sum('amount'))['total'] or 0
#     total_profit = total_sales - total_expenses

#     context = {
#         "total_sales": total_sales,
#         "total_expenses": total_expenses,
#         "total_profit": total_profit,
#     }
#     return render(request, "analytics/overview.html", context)