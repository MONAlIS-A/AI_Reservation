from django.db import migrations

def create_rooftop_business(apps, schema_editor):
    Business = apps.get_model('business', 'Business')
    if not Business.objects.filter(name__iexact="rooftop").exists():
        Business.objects.create(
            name="rooftop",
            website_url="https://www.rooftop.com",
            description="Our primary business focus is rooftop hosting and enjoyment.",
            domain="Hospitality & Leisure"
        )

def remove_rooftop_business(apps, schema_editor):
    Business = apps.get_model('business', 'Business')
    Business.objects.filter(name__iexact="rooftop").delete()

class Migration(migrations.Migration):

    dependencies = [
        ('business', '0010_appointment_service_name'),
    ]

    operations = [
        migrations.RunPython(create_rooftop_business, remove_rooftop_business),
    ]
