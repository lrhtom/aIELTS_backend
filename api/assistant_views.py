from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import status
from .models import UserTodoItem, UserShortcut
from .serializers import UserTodoItemSerializer, UserShortcutSerializer

class UserTodoItemViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserTodoItemSerializer

    def get_queryset(self):
        return UserTodoItem.objects.filter(user=self.request.user).order_by('created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        
    @action(detail=False, methods=['post'])
    def clear_completed(self, request):
        self.get_queryset().filter(done=True).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class UserShortcutViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserShortcutSerializer

    def get_queryset(self):
        return UserShortcut.objects.filter(user=self.request.user).order_by('created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
