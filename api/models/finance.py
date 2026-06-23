"""Money: AT-coin transaction log + store products + cart.

`TransactionRecord.record()` is the canonical atomic deduct/refund primitive — every
balance-changing path in the codebase should funnel through it.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .user import User


class StoreProduct(models.Model):
    name = models.CharField(max_length=100, verbose_name="商品名称")
    description = models.TextField(blank=True, verbose_name="商品描述")
    price_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="价格数值")
    price_currency = models.CharField(max_length=10, choices=[('CNY', '人民币'), ('AT_COIN', 'AT币')], default='CNY', verbose_name="货币类型")
    reward_type = models.CharField(max_length=20, default='AT_COIN', verbose_name="发货类型")
    reward_amount = models.IntegerField(default=0, verbose_name="发货数量(如AT币数量)")
    is_active = models.BooleanField(default=True, verbose_name="是否上架")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 'store_products'
        verbose_name = '商品'
        verbose_name_plural = '商品列表'

    def __str__(self):
        return f'{self.name} - {self.price_amount} {self.price_currency}'


class CartItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart_items', verbose_name='用户')
    product = models.ForeignKey(StoreProduct, on_delete=models.CASCADE, related_name='cart_entries', verbose_name='商品')
    quantity = models.IntegerField(default=1, verbose_name='数量')
    added_at = models.DateTimeField(auto_now_add=True, verbose_name='加入时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'store_cart_items'
        verbose_name = '购物车项目'
        verbose_name_plural = '购物车项目列表'
        unique_together = ('user', 'product')

    def __str__(self):
        return f'{self.user.username} -> {self.product.name} x{self.quantity}'


class TransactionRecord(models.Model):
    class Currency(models.TextChoices):
        AT_COIN = 'AT_COIN', _('AT币')
        CNY = 'CNY', _('现金(CNY)')

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    currency = models.CharField(max_length=20, choices=Currency.choices, default=Currency.AT_COIN, verbose_name="货币类型")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="交易金额", help_text="正数表示增加，负数表示扣除")
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="交易后余额")
    description = models.CharField(max_length=255, verbose_name="交易描述")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        db_table = 'finance_transaction_records'
        verbose_name = '交易记录'
        verbose_name_plural = '交易记录'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'currency', 'created_at'], name='idx_txn_user_cur_date'),
        ]

    def __str__(self):
        return f'{self.user.username} {self.amount} {self.currency} - {self.description}'

    @classmethod
    def record(cls, user, currency, amount, description):
        from django.db import transaction
        with transaction.atomic():
            # select_for_update locks the user row so concurrent AT_COIN credits/debits
            # cannot race past each other into double-deductions or stale balance_after.
            db_user = User.objects.select_for_update().get(pk=user.pk)

            if currency == cls.Currency.AT_COIN:
                db_user.at_balance += amount
                db_user.save(update_fields=['at_balance'])
                balance_after = db_user.at_balance
                # Mirror the new balance back onto the caller's instance so they can read it.
                user.at_balance = db_user.at_balance
            else:
                last_tx = cls.objects.filter(user=db_user, currency=currency).order_by('-created_at').first()
                balance_after = (last_tx.balance_after if last_tx else 0) + amount

            return cls.objects.create(
                user=db_user,
                currency=currency,
                amount=amount,
                balance_after=balance_after,
                description=description,
            )
