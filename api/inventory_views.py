"""Backpack (user inventory) read API. Item display text/icons are localised on
the frontend keyed by ``item_type``; the backend returns only type + quantity."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import UserItem


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def backpack(request):
    """当前用户拥有的物品（仅返回数量 > 0 的）。"""
    items = UserItem.objects.filter(user=request.user, quantity__gt=0).order_by('item_type')
    data = [{'item_type': it.item_type, 'quantity': it.quantity} for it in items]
    return Response({'items': data})
