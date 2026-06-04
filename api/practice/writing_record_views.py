import json
from django.http import JsonResponse
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from api.models import WritingServiceRecord

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def writing_records_list(request):
    if request.method == 'GET':
        service_type = request.GET.get('service_type', '')
        search = request.GET.get('search', '')
        
        queryset = WritingServiceRecord.objects.filter(user=request.user)
        
        if service_type:
            queryset = queryset.filter(service_type=service_type)
        if search:
            queryset = queryset.filter(title__icontains=search)
            
        records = queryset.order_by('-created_at')
        
        data = []
        for r in records:
            data.append({
                'id': r.id,
                'service_type': r.service_type,
                'title': r.title,
                'created_at': r.created_at.isoformat(),
            })
            
        return JsonResponse({'status': 'success', 'data': data})
        
    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            service_type = body.get('service_type')
            title = body.get('title')
            content = body.get('content')
            
            if not all([service_type, title, content]):
                return JsonResponse({'status': 'error', 'message': 'Missing required fields'}, status=400)
                
            record = WritingServiceRecord.objects.create(
                user=request.user,
                service_type=service_type,
                title=title,
                content=content
            )
            
            return JsonResponse({'status': 'success', 'id': record.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def writing_record_detail(request, record_id):
    try:
        record = WritingServiceRecord.objects.get(id=record_id, user=request.user)
    except WritingServiceRecord.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Record not found'}, status=404)
        
    if request.method == 'GET':
        return JsonResponse({
            'status': 'success',
            'data': {
                'id': record.id,
                'service_type': record.service_type,
                'title': record.title,
                'content': record.content,
                'created_at': record.created_at.isoformat(),
            }
        })
        
    elif request.method == 'DELETE':
        record.delete()
        return JsonResponse({'status': 'success', 'message': 'Deleted successfully'})
