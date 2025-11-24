from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from sales.models import Sale
from expenses.models import Expense
from inventory.models import Product
from django.db.models import Sum
from datetime import datetime, timedelta

# @login_required
def analytics_dashboard(request):
    # Sales & Expenses - last 7 days
    today = datetime.today()
    dates = [(today - timedelta(days=i)).date() for i in range(6, -1, -1)]

    sales_data = []
    expense_data = []
    profit_data = []

    for date in dates:
        sales_total = Sale.objects.filter(timestamp__date=date, created_by=request.user).aggregate(total=Sum('total_amount'))['total'] or 0
        expenses_total = Expense.objects.filter(timestamp__date=date, created_by=request.user).aggregate(total=Sum('amount'))['total'] or 0
        profit = sales_total - expenses_total

        sales_data.append(float(sales_total))
        expense_data.append(float(expenses_total))
        profit_data.append(float(profit))

    # Summary totals
    total_sales = sum(sales_data)
    total_expenses = sum(expense_data)
    total_profit = total_sales - total_expenses

    # Top 5 best-selling products
    top_products = (
        Product.objects.filter(created_by=request.user)
        .order_by('-quantity')[:5]
    )

    context = {
        "dates": [d.strftime("%b %d") for d in dates],
        "sales_data": sales_data,
        "expense_data": expense_data,
        "profit_data": profit_data,
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "total_profit": total_profit,
        "top_products": top_products,
    }
    return render(request, "analytics/dashboard.html", context)
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