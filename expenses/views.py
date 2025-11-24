from django.contrib import messages

from django.shortcuts import render, redirect
from urllib3 import request
from .models import Expense, ExpenseCategory
from .forms import ExpenseForm, ExpenseCategoryForm
from django.contrib.auth.decorators import login_required
from users.utils import has_any_group
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime

# if form.is_valid():
#     e = form.save(commit=False)
#     e.created_by = request.user
#     e.save()
#     messages.success(request, "Expense added successfully!")
#     return redirect("expense_list")
# else:
#     messages.error(request, "Failed to add expense. Please check your inputs.")


# @login_required
# @has_any_group("Admin","Staff")
def add_expense(request):
    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            e = form.save(commit=False)
            e.created_by = request.user
            e.save()
            return redirect("inventory_dashboard")
    else:
        form = ExpenseForm()
    return render(request, "expenses/add_expense.html", {"form": form})


# listing of expenses for current user
# @login_required
def expense_list(request):
    expenses = Expense.objects.filter(created_by=request.user).order_by("-timestamp")
    return render(request, "expenses/expense_list.html", {"expenses": expenses})


# categories
# @login_required
def expense_category_list(request):
    categories = ExpenseCategory.objects.all().order_by("name")
    return render(request, "expenses/expense_category_list.html", {"categories": categories})


# @login_required
def add_expense_category(request):
    if request.method == "POST":
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("expense_category_list")
    else:
        form = ExpenseCategoryForm()
    return render(request, "expenses/add_expense_category.html", {"form": form})


# expenses/views.py


def export_expenses_pdf(request):
    expenses = Expense.objects.all().order_by('-timestamp')

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, height - 50, "Expenses Report")
    p.setFont("Helvetica", 9)
    p.drawString(40, height - 65, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    y = height - 90
    p.setFont("Helvetica-Bold", 9)
    p.drawString(40, y, "Date")
    p.drawString(140, y, "Category")
    p.drawString(320, y, "Note")
    p.drawRightString(width - 40, y, "Amount (₵)")
    p.line(35, y-3, width-35, y-3)
    y -= 14
    p.setFont("Helvetica", 9)

    for e in expenses:
        if y < 60:
            p.showPage()
            y = height - 40
        p.drawString(40, y, e.timestamp.strftime("%Y-%m-%d %H:%M"))
        p.drawString(140, y, e.category.name if e.category else "—")
        p.drawString(320, y, (e.note[:30] + '...') if e.note and len(e.note) > 30 else (e.note or "—"))
        p.drawRightString(width - 40, y, f"{float(e.amount):.2f}")
        y -= 12

    p.showPage()
    p.save()
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="expenses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"'
    return response

 
 
