from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from api.models import StoreProduct, CartItem

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_products(request):
    products = StoreProduct.objects.filter(is_active=True).order_by('price_amount')
    data = []
    for p in products:
        data.append({
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price_amount': str(p.price_amount),
            'price_currency': p.price_currency,
            'reward_type': p.reward_type,
            'reward_amount': p.reward_amount,
        })
    return Response({'products': data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_product(request):
    product_id = request.data.get('product_id')
    if not product_id:
        return Response({'error': '缺少商品ID参数'}, status=400)

    try:
        product = StoreProduct.objects.get(id=product_id, is_active=True)
    except StoreProduct.DoesNotExist:
        return Response({'error': '在此平台找不到该商品或已下架'}, status=404)

    user = request.user

    if user.is_staff or user.is_superuser:
        # 管理员结账特权，直接发货
        if product.reward_type == 'AT_COIN':
            with transaction.atomic():
                user.at_balance += product.reward_amount
                user.save(update_fields=['at_balance'])
            return Response({
                'message': '你是管理员，已为你免单并成功发货。',
                'new_balance': user.at_balance
            })
        else:
            return Response({'error': f'未知的发货类型: {product.reward_type}'}, status=400)
            
    else:
        # 普通用户
        if product.price_currency == 'CNY':
            return Response({'error': '暂未开放真实支付网关，非管理员无法充值'}, status=403)
        elif product.price_currency == 'AT_COIN':
            # 使用 AT 币购买商品（预留能力）
            if user.at_balance < product.price_amount:
                return Response({'error': 'AT币余额不足'}, status=402)
            with transaction.atomic():
                user.at_balance -= int(product.price_amount)
                if product.reward_type == 'VIP':
                    pass  # handle VIP
                user.save()
            return Response({'message': '购买成功', 'new_balance': user.at_balance})
        else:
            return Response({'error': '未知的货币类型'}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cart_list(request):
    items = CartItem.objects.filter(user=request.user).select_related('product')
    data = []
    total_items = 0
    total_cny = 0.0
    for item in items:
        data.append({
            'cart_item_id': item.id,
            'product_id': item.product.id,
            'name': item.product.name,
            'price_amount': str(item.product.price_amount),
            'price_currency': item.product.price_currency,
            'quantity': item.quantity,
        })
        total_items += item.quantity
        if item.product.price_currency == 'CNY':
            total_cny += float(item.product.price_amount) * item.quantity

    return Response({
        'items': data,
        'total_items': total_items,
        'total_cny': str(round(total_cny, 2))
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cart_add(request):
    product_id = request.data.get('product_id')
    quantity = int(request.data.get('quantity', 1))
    
    if not product_id or quantity <= 0:
        return Response({'error': '无效的参数'}, status=400)
        
    try:
        product = StoreProduct.objects.get(id=product_id, is_active=True)
    except StoreProduct.DoesNotExist:
        return Response({'error': '在此平台找不到该商品或已下架'}, status=404)
        
    cart_item, created = CartItem.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'quantity': quantity}
    )
    if not created:
        cart_item.quantity += quantity
        cart_item.save(update_fields=['quantity'])
        
    return Response({'message': '成功加入购物车', 'quantity': cart_item.quantity})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cart_remove(request):
    product_id = request.data.get('product_id')
    quantity = int(request.data.get('quantity', 1))
    delete_all = request.data.get('delete_all', False)
    
    try:
        cart_item = CartItem.objects.get(user=request.user, product_id=product_id)
    except CartItem.DoesNotExist:
        return Response({'error': '购物车内无此商品'}, status=404)
        
    if delete_all or cart_item.quantity <= quantity:
        cart_item.delete()
        new_quantity = 0
    else:
        cart_item.quantity -= quantity
        cart_item.save(update_fields=['quantity'])
        new_quantity = cart_item.quantity
        
    return Response({'message': '成功移除或减少数量', 'quantity': new_quantity})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cart_checkout(request):
    user = request.user
    items = CartItem.objects.filter(user=user).select_related('product')
    
    if not items.exists():
        return Response({'error': '购物车为空'}, status=400)
        
    if user.is_staff or user.is_superuser:
        total_at_reward = 0
        with transaction.atomic():
            for item in items:
                if item.product.reward_type == 'AT_COIN':
                    total_at_reward += item.product.reward_amount * item.quantity
                
            user.at_balance += total_at_reward
            user.save(update_fields=['at_balance'])
            items.delete()
            
        return Response({
            'message': '你是管理员，已为你购物车内商品全额免单并成功发货。',
            'new_balance': user.at_balance
        })
    else:
        # 简单判定：只要购物车内有 CNY 计价商品，就先拦截。
        has_cny = any(item.product.price_currency == 'CNY' for item in items)
        if has_cny:
            return Response({'error': '暂未开放真实支付网关，非管理员无法充值'}, status=403)
            
        # 预留：AT 币结算逻辑
        total_at_cost = sum(item.product.price_amount * item.quantity for item in items if item.product.price_currency == 'AT_COIN')
        if user.at_balance < total_at_cost:
            return Response({'error': 'AT币余额不足以支付纯 AT 币商品'}, status=402)
            
        with transaction.atomic():
            user.at_balance -= int(total_at_cost)
            # handle rewards
            for item in items:
                if item.product.reward_type == 'VIP':
                    pass
            user.save(update_fields=['at_balance'])
            items.delete()
            
        return Response({'message': '结账成功', 'new_balance': user.at_balance})



