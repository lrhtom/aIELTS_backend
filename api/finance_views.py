from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import serializers
from django.db.models import Sum
from django.db.models.functions import TruncDate
from api.models import TransactionRecord
from datetime import timedelta
from django.utils import timezone

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionRecord
        fields = ['id', 'currency', 'amount', 'balance_after', 'description', 'created_at']

class TransactionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class TransactionListView(generics.ListAPIView):
    """
    Get paginated transaction history for the logged-in user.
    Can filter by currency.
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = TransactionPagination

    def get_queryset(self):
        qs = TransactionRecord.objects.filter(user=self.request.user)
        currency = self.request.query_params.get('currency')
        if currency:
            qs = qs.filter(currency=currency)
        return qs.order_by('-created_at')

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def finance_stats(request):
    """
    Get aggregated finance stats:
    - Total AT used (sum of negative AT transactions)
    - Total Cash used (sum of negative CNY transactions)
    - Daily aggregation for the last 30 days
    """
    user = request.user
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    # 1. Total Used (Sum of negative transactions)
    at_total_used = TransactionRecord.objects.filter(
        user=user, currency=TransactionRecord.Currency.AT_COIN, amount__lt=0
    ).aggregate(total=Sum('amount'))['total'] or 0

    cny_total_used = TransactionRecord.objects.filter(
        user=user, currency=TransactionRecord.Currency.CNY, amount__lt=0
    ).aggregate(total=Sum('amount'))['total'] or 0

    # 2. Daily Usage (Sum of negative amounts per day, inverted to positive for display)
    daily_stats = TransactionRecord.objects.filter(
        user=user,
        amount__lt=0,
        created_at__gte=thirty_days_ago
    ).annotate(
        date=TruncDate('created_at')
    ).values('date', 'currency').annotate(
        daily_used=Sum('amount')
    ).order_by('date')

    # Reformat the grouped data for charting
    # Expected output: [{ date: '2026-06-01', at_used: 100, cny_used: 0 }, ...]
    # We will build a dictionary keyed by date string
    chart_data = {}
    for stat in daily_stats:
        date_str = stat['date'].strftime('%Y-%m-%d')
        if date_str not in chart_data:
            chart_data[date_str] = {'date': date_str, 'at_used': 0, 'cny_used': 0}
        
        # Invert negative amount for positive display on the chart
        amount = abs(float(stat['daily_used']))
        if stat['currency'] == TransactionRecord.Currency.AT_COIN:
            chart_data[date_str]['at_used'] = amount
        elif stat['currency'] == TransactionRecord.Currency.CNY:
            chart_data[date_str]['cny_used'] = amount

    # Sort by date
    sorted_chart_data = [chart_data[d] for d in sorted(chart_data.keys())]

    return Response({
        'total_at_used': abs(float(at_total_used)),
        'total_cny_used': abs(float(cny_total_used)),
        'daily_usage': sorted_chart_data
    })
