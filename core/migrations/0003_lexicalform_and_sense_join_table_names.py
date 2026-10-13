from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_lexicalentry_lexicalentrysubcategory_lexicalrelation_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LexicalForm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('form', models.TextField(verbose_name='Форма')),
                ('accent', models.TextField(blank=True, null=True, verbose_name='Форма с ударением')),
                ('grammatical_features', models.TextField(blank=True, null=True, verbose_name='Грамматические характеристики')),
                ('lexical_entry', models.ForeignKey(db_column='lexical_entry_id', on_delete=django.db.models.deletion.CASCADE, related_name='lexical_forms', to='core.lexicalentry')),
            ],
            options={
                'verbose_name': 'Форма лексемы',
                'verbose_name_plural': 'Формы лексем',
                'db_table': 'LexicalForm',
                'managed': False,
            },
        ),
        migrations.AlterModelTable(
            name='sensetext',
            table='Sense_Text',
        ),
        migrations.AlterModelTable(
            name='sensesubcategory',
            table='Sense_Subcategory',
        ),
    ]
