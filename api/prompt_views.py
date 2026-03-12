from django.db.models import Count
from django.core.paginator import Paginator, EmptyPage
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import AIPrompt


def _serialize_prompt(prompt, user):
    return {
        "id": prompt.id,
        "username": prompt.username,
        "title": prompt.title,
        "prompt_content": prompt.prompt_content,
        "created_at": prompt.created_at.isoformat(),
        "like_count": prompt.likes.count(),
        "favorite_count": prompt.favorites.count(),
        "is_liked": prompt.likes.filter(id=user.id).exists(),
        "is_favorited": prompt.favorites.filter(id=user.id).exists(),
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def prompt_list(request):
    """
    GET:  获取提示词列表，支持 ?page=1&sort=latest|popular
    POST: 新增一条提示词 {"title": "xxx", "prompt_content": "xyz"}
    """
    if request.method == "GET":
        page_num = request.GET.get('page', 1)
        sort = request.GET.get('sort', 'latest')

        prompt_qs = AIPrompt.objects.all()
        if sort == 'popular':
            prompt_qs = prompt_qs.annotate(like_cnt=Count('likes')).order_by('-like_cnt', '-created_at')
        else:
            prompt_qs = prompt_qs.order_by('-created_at')

        paginator = Paginator(prompt_qs, 20)

        try:
            page_obj = paginator.page(page_num)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        except ValueError:
            page_obj = paginator.page(1)

        data = [_serialize_prompt(p, request.user) for p in page_obj.object_list]

        return JsonResponse({
            "data": data,
            "current_page": page_obj.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count
        })

    elif request.method == "POST":
        try:
            title = request.data.get('title', '').strip()
            prompt_content = request.data.get('prompt_content', '').strip()

            if not title or not prompt_content:
                return JsonResponse({"error": "标题和提示词内容不能为空"}, status=400)

            new_prompt = AIPrompt.objects.create(
                username=request.user.username,
                title=title,
                prompt_content=prompt_content
            )
            return JsonResponse({
                "message": "创建成功",
                "id": new_prompt.id
            }, status=201)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def prompt_like(request, pk):
    """切换点赞状态"""
    try:
        prompt = AIPrompt.objects.get(pk=pk)
    except AIPrompt.DoesNotExist:
        return JsonResponse({"error": "提示词不存在"}, status=404)

    user = request.user
    if prompt.likes.filter(id=user.id).exists():
        prompt.likes.remove(user)
        liked = False
    else:
        prompt.likes.add(user)
        liked = True

    return JsonResponse({
        "liked": liked,
        "like_count": prompt.likes.count()
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def prompt_favorite(request, pk):
    """切换收藏状态"""
    try:
        prompt = AIPrompt.objects.get(pk=pk)
    except AIPrompt.DoesNotExist:
        return JsonResponse({"error": "提示词不存在"}, status=404)

    user = request.user
    if prompt.favorites.filter(id=user.id).exists():
        prompt.favorites.remove(user)
        favorited = False
    else:
        prompt.favorites.add(user)
        favorited = True

    return JsonResponse({
        "favorited": favorited,
        "favorite_count": prompt.favorites.count()
    })
