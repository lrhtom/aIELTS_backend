from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.models import User
from api.serializers import UserSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_balance(request):
    """获取当前用户的 AT 币余额。"""
    user = request.user
    return Response({
        'atBalance': user.at_balance,
        'currentBalance': user.at_balance,
        'username': user.username,
        'email': user.email
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_balance(request):
    """检查 AT 币余额是否足够。"""
    user = request.user
    required_amount = request.data.get('required_amount', 0)

    if user.at_balance >= required_amount:
        return Response({
            'ok': True,
            'currentBalance': user.at_balance,
            'requiredBalance': required_amount
        })
    else:
        return Response({
            'ok': False,
            'currentBalance': user.at_balance,
            'requiredBalance': required_amount,
            'message': f'AT币余额不足，需要 {required_amount} AT，当前余额 {user.at_balance} AT'
        }, status=402)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def consume_at(request):
    """消费 AT 币。"""
    user = request.user
    amount = request.data.get('amount', 0)
    description = request.data.get('description', '')
    service_type = request.data.get('service_type', '')

    if amount <= 0:
        return Response({'error': '消费金额必须大于 0'}, status=400)

    if user.at_balance < amount:
        return Response({
            'error': f'AT币余额不足，需要 {amount} AT，当前余额 {user.at_balance} AT',
            'requiredBalance': amount,
            'currentBalance': user.at_balance
        }, status=402)

    # 扣除 AT 币
    from api.models import TransactionRecord
    TransactionRecord.record(user, TransactionRecord.Currency.AT_COIN, -amount, description or f"{service_type} 消费")

    return Response({
        'ok': True,
        'newBalance': user.at_balance,
        'consumed': amount,
        'description': description,
        'serviceType': service_type
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_at(request):
    """增加 AT 币（充值或奖励）。"""
    user = request.user
    amount = request.data.get('amount', 0)
    description = request.data.get('description', '')
    transaction_type = request.data.get('transaction_type', 'reward')

    if amount <= 0:
        return Response({'error': '金额必须大于 0'}, status=400)

    # 增加 AT 币
    from api.models import TransactionRecord
    TransactionRecord.record(user, TransactionRecord.Currency.AT_COIN, amount, description or f"{transaction_type} 增加")

    return Response({
        'ok': True,
        'newBalance': user.at_balance,
        'added': amount,
        'description': description,
        'transactionType': transaction_type
    })

