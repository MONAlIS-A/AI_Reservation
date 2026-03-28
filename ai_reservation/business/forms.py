from django import forms
from .models import Business

class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['name', 'website_url', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Acme Corporation'}),
            'website_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.yourbusiness.com'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Describe your primary business focus...', 'rows': 4}),
        }
