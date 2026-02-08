import blog
from django import views
from django.core import paginator
from django.http import HttpResponseRedirect, Http404
from django.db.models.fields import EmailField
from django.shortcuts import render, redirect,get_object_or_404
from django.views import View
from .models import Blog, Catagory, Tag, EmailSignUp, Comment, Like, PostView, PostFirstView
from dashboard.models import Author
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone


class HomeView(View):
    def get(self,request,*args,**kwargs):
        '''
        # featured_post = Blog.objects.filter(featured=True, status='active',show_hide='show').order_by('-id')
        # catagories_obj  = Catagory.objects.all().order_by('-id')
        # tags_obj = Tag.objects.all().order_by('-id')
        # blog_post  = Blog.objects.filter(status='active',show_hide='show').order_by('-id')
        # popular_post = blog_post[:3]
        # images_obj = blog_post.only('image').order_by('-id')[:6]
        # #all_post = Blog.objects.all().order_by('-id')
        # # pagination Logics
        # paginator = Paginator(all_post, 4)
        # page_number = request.GET.get('page')
        # page_obj = paginator.get_page(page_number)

        # context = {
        #     'featured':featured_post,
        #     'popular': popular_post,
        #     'catagories':catagories_obj,
        #     'tags':tags_obj,
        #     'image':images_obj,
        #     'post':page_obj

        # }
        '''
        featured_obj = Blog.objects.all().filter(status='active', visible=True, featured=True).order_by('catagories','-created_at')[:5]
        post_obj = Blog.objects.all().filter(status='active', visible=True).order_by('catagories','-created_at')
        # As per Templates Views — safe indexing when fewer than 2 featured posts
        featured_list = list(featured_obj)
        first_post = featured_list[0] if len(featured_list) > 0 else None
        s_post = featured_list[1] if len(featured_list) > 1 else (featured_list[0] if len(featured_list) == 1 else None)
        last_post = featured_list[2:] if len(featured_list) > 2 else []
        context={
            'post':post_obj,
            'f_post':featured_obj,
            'first':first_post,
            's_post':s_post,
            'last_post':last_post
            
        }
        return render(request, 'home/index.html',context)

# single blog views
class SingleBlogView(View):
    def get(self,request,id,*args,**kwargs):
        post_obj = get_object_or_404(Blog, id=id)

        # Only owners or staff can view non-active/hidden posts (drafts, pending, or manually hidden)
        user = request.user
        # Compare post author's User to request user (avoids touching request.user.author which can raise if no Author profile)
        is_owner = user.is_authenticated and post_obj.author.author_id == user.pk
        if not (post_obj.status == 'active' and post_obj.visible) and not (
            is_owner or user.is_staff or user.is_superuser
        ):
            raise Http404("Post not found")

        # Viewer's author profile (for likes and view count); safe when user has no Author
        if request.user.is_authenticated:
            try:
                author = request.user.author
            except Author.DoesNotExist:
                author = None
        else:
            author = None
        # Count view only for other users (not the post author): (1) not chart partial request, (2) post active/visible,
        # (3) viewer did not write the post, (4) first time this user/session views this post.
        # Only skip when ?partial=1 is in URL (chart AJAX); do not use X-Requested-With so normal page loads always count.
        is_chart_partial = request.GET.get('partial') == '1'
        viewer_is_post_author = is_owner  # post author's User == request.user
        should_count_view = (
            not is_chart_partial
            and post_obj.status == 'active'
            and post_obj.visible
            and not viewer_is_post_author
        )
        if should_count_view:
            first_time = False
            if request.user.is_authenticated:
                pfv, created = PostFirstView.objects.get_or_create(
                    post=post_obj, user=request.user
                )
                first_time = created
            else:
                viewed = request.session.get('viewed_post_ids')
                if viewed is None:
                    viewed = []
                if post_obj.id not in viewed:
                    first_time = True
                    viewed = list(viewed) + [post_obj.id]
                    request.session['viewed_post_ids'] = viewed
                    request.session.modified = True
            if first_time:
                post_obj.visit_count = post_obj.visit_count + 1
                post_obj.save(update_fields=['visit_count'])
                today = timezone.now().date()
                daily_view, _ = PostView.objects.get_or_create(post=post_obj, date=today)
                daily_view.views = daily_view.views + 1
                daily_view.save(update_fields=['views'])
        can_like = author is not None and post_obj.author != author
        user_has_liked = False
        user_reaction = None
        if can_like:
            existing_like = Like.objects.filter(post=post_obj, author=author).first()
            if existing_like:
                user_has_liked = existing_like.reaction != 'dislike'
                user_reaction = existing_like.reaction
        likes_count = post_obj.likes.exclude(reaction='dislike').count()

        # views graph: last 1, 3, or 7 days (from ?views_range=1|3|7)
        from datetime import timedelta
        today = timezone.now().date()
        views_range = request.GET.get('views_range', '7')
        if views_range not in ('1', '3', '7'):
            views_range = '7'
        num_days = int(views_range)
        days = []
        max_views = 0
        for i in range(num_days - 1, -1, -1):
            day = today - timedelta(days=i)
            pv = PostView.objects.filter(post=post_obj, date=day).first()
            views = pv.views if pv else 0
            days.append({'date': day, 'views': views})
            if views > max_views:
                max_views = views
        period_total = sum(d['views'] for d in days)
        for d in days:
            if max_views > 0:
                d['height'] = int((d['views'] / float(max_views)) * 100)
            else:
                d['height'] = 0
        views_range_label = {'1': 'Today', '3': 'Last 3 days', '7': 'Last 7 days'}.get(views_range, 'Last 7 days')
        approved_comments = post_obj.comments.filter(is_approved=True)
        releted_post = Blog.objects.filter(author=post_obj.author, status='active', visible=True).exclude(id=id).order_by('-id')[:4]
        # As per templates views 
        first_post = releted_post.first()
        last_post  = releted_post[1:]
        # do not show views/likes for draft or pending posts
        show_views_likes = post_obj.status == 'active' and post_obj.visible
        if show_views_likes:
            display_visit_count = post_obj.visit_count
            display_weekly_total = period_total
            display_likes_count = likes_count
            display_weekly_views = days
        else:
            display_visit_count = 0
            display_weekly_total = 0
            display_likes_count = 0
            display_weekly_views = []

        context ={
            'post':post_obj,
            'r_post':releted_post,
            'first':first_post,
            'last':last_post,
            'can_like': can_like,
            'user_has_liked': user_has_liked,
            'user_reaction': user_reaction,
            'likes_count': display_likes_count,
            'comments': approved_comments,
            'weekly_views': display_weekly_views,
            'weekly_total': display_weekly_total,
            'views_range': views_range,
            'views_range_label': views_range_label,
            'show_views_likes': show_views_likes,
            'display_visit_count': display_visit_count,
        }
        if request.GET.get('partial') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'blogs/post/single_blog_chart_partial.html', context)
        return render(request,'blogs/post/single_blog.html', context)


class AuthorProfileView(View):
    def get(self, request, username, *args, **kwargs):
        author = get_object_or_404(Author, author__username=username)
        posts = Blog.objects.filter(
            author=author,
            status='active',
            visible=True
        ).order_by('-created_at')
        total_views = posts.aggregate(total=Sum('visit_count'))['total'] or 0

        context = {
            "author_profile": author,
            "posts": posts,
            "total_views": total_views,
        }
        return render(request, "home/author_profile.html", context)

# Catagory View
class CatagoryView(View):
    def get(self, request, slug, *args, **kwargs):
        catagory_obj = get_object_or_404(Catagory, slug=slug)
        #post = catagory_obj.blog_set.all().order_by('-id')
        post = Blog.objects.filter(catagories= catagory_obj,\
            status='active',visible=True)\
            .order_by('-created_at')
        popular = Blog.objects.filter(catagories= catagory_obj,\
            status='active',visible=True)\
            .annotate(post_count=Count('visit_count'))\
            .order_by('-visit_count')
        # as Per templates views
        featured_post = popular.first()
        popular_post = popular[1:6]
        # Pagination 
        paginator = Paginator(post, 3)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        context ={
            'catagory':catagory_obj,
            'post':page_obj,
            'pop':popular_post,
            'f_post':featured_post,
        }
        return render(request,'blogs/category/category.html', context )

# tag View
class TagView(View):
    def get(self,request,id,*args,**kwargs):
        tag_obj = get_object_or_404(Tag, id=id)
        post = tag_obj.blog_set.filter(status='active', visible=True).order_by('-id')
        tag_count = post.count()
        context={
            'tag':tag_obj,
            'post':post,
            'tag_count':tag_count
        }
        return render(request,'home/tag.html',context)

# Subscribe Views
class SubsCribe(View):
    def post(self, request,*args,**kwargs):
        sub_obj = request.POST.get('subscribe')
        email = EmailSignUp.objects.filter(email=sub_obj)
        if email :
            messages.success(request,'You are already Subscribed , Thanks!')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
        else:
            subscribe = EmailSignUp.objects.create(email=sub_obj)
            subscribe.save()
            messages.success(request,'Thanks for Subscribing')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

# search Views
class SearchView(View):
    def get(self,request,*args,**kwargs):
        search = request.GET['q']
        post = Blog.objects.filter(status='active',visible=True)
        if len(search) > 100:
            posts = post.none()
        else:
            posts = post.filter(
                Q(title__icontains=search) |
                Q(catagories__name__icontains=search) |
                Q(detail__icontains = search)
                
            )
        context ={
            'post':posts,
            'search':search
        }
        return render(request,'home/search.html', context)

# Comments View — only logged-in users; name is set from request.user
class CommentView(View):
    def post(self, request, id, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to comment.')
            return redirect('login')
        post = get_object_or_404(Blog, id=id)
        body = (request.POST.get('body') or '').strip()
        if not body:
            messages.error(request, 'Comment cannot be empty.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
        # name filled automatically from logged-in user (matches "Comment as ..." in template)
        name = request.user.username
        comment_obj = Comment(post=post, name=name, body=body, is_approved=False)
        comment_obj.save()
        messages.success(
            request,
            'Your comment has been sent to the author and is awaiting approval.'
        )
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

# Likes View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Blog, Like

class LikeToggleView(View):
    def post(self, request, id):
        post = get_object_or_404(Blog, id=id)

        # ensure only logged-in authors can like posts
        if not request.user.is_authenticated or not hasattr(request.user, "author"):
            return JsonResponse(
                {
                    "error": "Authentication as an author is required to like posts.",
                    "liked": False,
                    "likes_count": post.likes.exclude(reaction='dislike').count(),
                },
                status=403,
            )

        # optionally guard against liking non-active / hidden posts
        if not (post.status == "active" and post.visible):
            return JsonResponse(
                {
                    "error": "You can only like published and visible posts.",
                    "liked": False,
                    "likes_count": post.likes.exclude(reaction='dislike').count(),
                },
                status=400,
            )

        author = request.user.author
        # authors cannot like their own post
        if post.author == author:
            return JsonResponse(
                {
                    "error": "You cannot like your own post.",
                    "liked": False,
                    "likes_count": post.likes.exclude(reaction='dislike').count(),
                },
                status=400,
            )
        reaction = request.POST.get("reaction", "like")

        like, created = Like.objects.get_or_create(
            post=post,
            author=author,
            defaults={"reaction": reaction},
        )

        if not created:
            if like.reaction == reaction:
                # clicking same reaction again removes it
                like.delete()
                liked = False
                current_reaction = None
            else:
                like.reaction = reaction
                like.save()
                liked = reaction != "dislike"
                current_reaction = like.reaction
        else:
            liked = reaction != "dislike"
            current_reaction = like.reaction

        likes_count = post.likes.exclude(reaction='dislike').count()

        return JsonResponse({
            "liked": liked,
            "reaction": current_reaction,
            "likes_count": likes_count,
        })

def test(request):
    catagory_obj = Catagory.objects.all()
    cat = Catagory.objects.all().count()
    lent = len(catagory_obj)
    post = Catagory.objects.all() \
        .annotate(post_count=Count('blog'))\
        .order_by('-post_count')
    context = {
        'catagory':catagory_obj,
        'cat':cat,
        'lent':lent,
        'post':post
        
        
    }
    return render(request,'test.html', context)

