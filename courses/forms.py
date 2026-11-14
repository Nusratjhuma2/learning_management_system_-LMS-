from decimal import Decimal
from django import forms
from django.utils.text import slugify

from .models import Course


class CourseForm(forms.ModelForm):
    """
    Form for creating and editing courses with full pricing,
    monetization controls, and academic curriculum metadata.
    """

    class Meta:
        model = Course
        fields = [
            'title',
            'slug',
            'category',
            'level',
            'language',
            'is_free',
            'price',
            'discount_price',
            'preview_video_url',
            'description',
            'what_you_will_learn',
            'requirements',
            'thumbnail',
            'status',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Enterprise Distributed Systems & Cloud Architecture',
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., enterprise-cloud-architecture (leave blank to auto-generate)',
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'level': forms.Select(attrs={'class': 'form-select'}),
            'language': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., English',
            }),
            'is_free': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
                'id': 'id_is_free',
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.00',
                'placeholder': '49.99',
                'id': 'id_price',
            }),
            'discount_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.00',
                'placeholder': '29.99 (Optional)',
                'id': 'id_discount_price',
            }),
            'preview_video_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://www.youtube.com/watch?v=... or preview stream URL',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Comprehensive academic overview and syllabus objectives...',
            }),
            'what_you_will_learn': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Key learning outcomes (one per line)...',
            }),
            'requirements': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Prerequisites and required background knowledge...',
            }),
            'thumbnail': forms.FileInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'is_free': 'Offer this course for Free',
            'price': 'Standard Tuition Price ($ USD)',
            'discount_price': 'Discounted / Promotional Price ($ USD)',
            'preview_video_url': 'Trailer / Preview Video URL',
            'what_you_will_learn': 'What Students Will Learn',
            'requirements': 'Prerequisites & Requirements',
        }
        help_texts = {
            'is_free': 'Check this option to offer unrestricted, complimentary enrollment.',
            'price': 'Base enrollment fee for paid admission.',
            'discount_price': 'Optional sale price. If set, must be strictly lower than standard price.',
            'slug': 'URL identifier. Leave blank to automatically generate from course title.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['price'].required = False
        self.fields['discount_price'].required = False
        self.fields['preview_video_url'].required = False
        self.fields['what_you_will_learn'].required = False
        self.fields['requirements'].required = False
        self.fields['category'].required = False

    def clean(self):
        cleaned_data = super().clean()
        is_free = cleaned_data.get('is_free', False)
        price = cleaned_data.get('price')
        discount_price = cleaned_data.get('discount_price')
        title = cleaned_data.get('title', '')
        slug = cleaned_data.get('slug', '').strip()

        # Auto-generate unique slug if omitted
        if not slug and title:
            base_slug = slugify(title)
            slug = base_slug
            counter = 1
            qs = Course.objects.filter(slug=slug)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            while qs.exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                qs = Course.objects.filter(slug=slug)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
            cleaned_data['slug'] = slug
        elif slug:
            qs = Course.objects.filter(slug=slug)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('slug', f"A course with slug '{slug}' already exists. Please choose a different slug.")

        # Pricing validation logic
        if is_free:
            cleaned_data['price'] = Decimal('0.00')
            cleaned_data['discount_price'] = None
        else:
            if price is None or price <= Decimal('0.00'):
                self.add_error(
                    'price',
                    'Please specify a regular course price greater than $0.00, or check "Offer this course for Free".'
                )
            if discount_price is not None:
                if discount_price <= Decimal('0.00'):
                    self.add_error('discount_price', 'Discount price must be greater than $0.00.')
                elif price is not None and discount_price >= price:
                    self.add_error(
                        'discount_price',
                        f'Discount price (${discount_price:.2f}) must be strictly less than the standard price (${price:.2f}).'
                    )

        return cleaned_data
