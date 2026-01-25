# # sales/utils.py (or users/utils.py)
# from users.utils import is_super_admin, is_sub_admin

# def visible_queryset_for_user(qs, user):
#     """
#     SuperAdmin sees all.
#     SubAdmin sees only what THEY created.
#     Other roles can use their own logic.
#     """
#     if is_super_admin(user):
#         return qs
#     if is_sub_admin(user):
#         return qs.filter(created_by=user)
#     return qs
# # usage example:
# # from sales.utils import visible_queryset_for_user