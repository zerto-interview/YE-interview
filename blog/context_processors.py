# for blog views  global varibale calls
from .models import Catagory, Blog
from django.db.models import Count, Q
from django.utils.text import slugify


def _ensure_category_slugs():
    """Ensure all categories have a slug (for topic URLs and nav links)."""
    for cat in Catagory.objects.filter(Q(slug__isnull=True) | Q(slug='')):
        if cat.name:
            cat.slug = slugify(cat.name) or f'category-{cat.id}'
            cat.save(update_fields=['slug'])


def globalVariable(request):
    _ensure_category_slugs()
    # showing The categories with most post under each category
    category = Catagory.objects.all()\
        .annotate(post_count=Count('blog'))\
        .filter(blog__isnull=False)\
        .order_by('-post_count')[:4]
    category_count = category.count()
    context = {
        'category': category,
        'cat_count': category_count
    }
    return context
## Information
#.annotate(post_count=Count('blog'))\ -> countin the blog post under each category
#.filter(blog__isnull=False)\ -> Filtering the blog model so that category without post wont display
#.order_by('-post_count')[:5] -> ordering by most post , category with max posts will show first. 