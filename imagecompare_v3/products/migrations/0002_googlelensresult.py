"""
Run after adding GoogleLensResult to models.py:

    python manage.py makemigrations
    python manage.py migrate

Or copy this file to products/migrations/000X_add_googleLensresult.py
and run: python manage.py migrate
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Replace 'products' and '0001_initial' with your actual last migration
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='GoogleLensResult',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('result_type', models.CharField(choices=[('visual', 'Visual Match'), ('shopping', 'Shopping Result')], default='visual', max_length=10)),
                ('rank',        models.PositiveSmallIntegerField()),
                ('title',       models.CharField(blank=True, max_length=500)),
                ('link',        models.URLField(max_length=2000)),
                ('source',      models.CharField(blank=True, max_length=200)),
                ('thumbnail',   models.URLField(blank=True, max_length=2000)),
                ('price',       models.CharField(blank=True, max_length=50)),
                ('rating',      models.CharField(blank=True, max_length=20)),
                ('scraped',     models.BooleanField(default=False)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('search',      models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lens_results',
                    to='products.searchhistory',
                )),
            ],
            options={
                'ordering': ['result_type', 'rank'],
            },
        ),
    ]