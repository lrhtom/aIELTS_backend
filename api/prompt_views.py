import json
from django.core.paginator import Paginator, EmptyPage
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import AIPrompt

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def prompt_list(request):
    """
    GET: 获取提示词列表，支持 ?page=1
    POST: 新增一条提示词 {"username": "abc", "prompt_content": "xyz"}
    """
    if request.method == "GET":
        page_num = request.GET.get('page', 1)
        # 获取所有提示词（模型中自带按照 -created_at 倒序排列）
        prompt_qs = AIPrompt.objects.all()
        
        # 使用 Django Paginator 进行分页，每页 20 条
        paginator = Paginator(prompt_qs, 20)
        
        try:
            page_obj = paginator.page(page_num)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)  # 溢出时返回最后一页
        except ValueError:
            page_obj = paginator.page(1)
            
        data = []
        for p in page_obj.object_list:
            data.append({
                "id": p.id,
                "username": p.username,
                "prompt_content": p.prompt_content,
                "created_at": p.created_at.isoformat()
            })
            
        return JsonResponse({
            "data": data,
            "current_page": page_obj.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count
        })

    elif request.method == "POST":
        try:
            username = request.data.get('username', '').strip()
            prompt_content = request.data.get('prompt_content', '').strip()
            
            if not username or not prompt_content:
                return JsonResponse({"error": "用户名和提示词内容不能为空"}, status=400)
                
            new_prompt = AIPrompt.objects.create(
                username=username,
                prompt_content=prompt_content
            )
            return JsonResponse({
                "message": "创建成功",
                "id": new_prompt.id
            }, status=201)
            
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
