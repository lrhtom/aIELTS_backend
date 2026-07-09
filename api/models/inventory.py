"""Backpack / inventory: consumable items a user owns (e.g. makeup check-in cards).

Kept separate from ``finance`` because these are non-currency, per-type stackable
items surfaced in the profile Backpack tab. Use ``grant`` / ``consume`` as the
atomic primitives — never mutate ``quantity`` directly under concurrency.
"""
from django.db import models, transaction

from .user import User


class UserItem(models.Model):
    class ItemType(models.TextChoices):
        MAKEUP_CARD = 'makeup_card', '补签卡'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='items', verbose_name='用户')
    item_type = models.CharField(max_length=32, choices=ItemType.choices, verbose_name='物品类型')
    quantity = models.PositiveIntegerField(default=0, verbose_name='数量')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_items'
        verbose_name = '背包物品'
        verbose_name_plural = '背包物品'
        unique_together = ('user', 'item_type')

    def __str__(self):
        return f'{self.user.username} - {self.get_item_type_display()} x{self.quantity}'

    @classmethod
    def grant(cls, user, item_type, amount=1):
        """原子增加某物品数量，返回更新后的记录。"""
        with transaction.atomic():
            item, _ = cls.objects.select_for_update().get_or_create(
                user=user, item_type=item_type, defaults={'quantity': 0}
            )
            item.quantity += amount
            item.save(update_fields=['quantity', 'updated_at'])
            return item

    @classmethod
    def consume(cls, user, item_type, amount=1):
        """原子消耗某物品，库存足够返回 True，否则不扣减并返回 False。"""
        with transaction.atomic():
            item = cls.objects.select_for_update().filter(user=user, item_type=item_type).first()
            if not item or item.quantity < amount:
                return False
            item.quantity -= amount
            item.save(update_fields=['quantity', 'updated_at'])
            return True

    @classmethod
    def count(cls, user, item_type):
        """当前拥有数量（无记录视为 0）。"""
        item = cls.objects.filter(user=user, item_type=item_type).first()
        return item.quantity if item else 0
