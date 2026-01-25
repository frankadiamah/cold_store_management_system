# users/utils.py
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
 
 
def in_group(group_name):
    def predicate(user):
        if not user.is_authenticated:
            return False
        return user.groups.filter(name=group_name).exists() or user.is_superuser
    return user_passes_test(predicate)

def has_any_group(*group_names):
    def predicate(user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.groups.filter(name__in=group_names).exists()
    return user_passes_test(predicate)

# class-based view mixin:
class GroupRequiredMixin:
    required_groups = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        if not request.user.groups.filter(name__in=self.required_groups).exists():
            raise PermissionDenied("You do not have permission to access this resource.")
        return super().dispatch(request, *args, **kwargs)
# usage example:
# class MyView(GroupRequiredMixin, View):
#     required_groups = ['Admin', 'Staff']