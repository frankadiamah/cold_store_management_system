from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group

class EmployeeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="employee_profile")
    full_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ssnit_number = models.CharField(max_length=50, blank=True)
    photo = models.ImageField(upload_to="employees/", blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)


    def __str__(self):
        return self.full_name


class AttendanceLog(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="attendance")
    clock_in = models.DateTimeField()
    clock_out = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-clock_in"]
        
        

    def hours_worked(self):
        if self.clock_out:
            return (self.clock_out - self.clock_in).total_seconds() / 3600
        return 0

    def __str__(self):
        return f"{self.employee.full_name} @ {self.clock_in:%Y-%m-%d %H:%M}"
# Add the signal below your models. to add automatically add staff to users of staff group
@receiver(post_save, sender=EmployeeProfile)
def add_user_to_staff_group(sender, instance, created, **kwargs):
    if created:
        user = instance.user

        # Get or create Staff group
        staff_group, _ = Group.objects.get_or_create(name="Staff")

        # Add user to Staff group
        user.groups.add(staff_group)
# RESULT SO FAR

# ✔ Admin creates EmployeeProfile
# ✔ User is instantly:

# Linked to employee

# Added to Staff group

# Can clock in/out

# Can access Staff-only pages