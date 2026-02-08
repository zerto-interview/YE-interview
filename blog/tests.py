from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.db import IntegrityError
from datetime import timedelta

from django.contrib.auth.models import User
from dashboard.models import Author
from .models import Blog, Catagory, Tag, Like, PostView, PostFirstView, Comment
from .context_processors import _ensure_category_slugs, globalVariable


def make_author(username='author1', **kwargs):
    user = User.objects.create_user(username=username, password='testpass123', **kwargs)
    author = Author.objects.create(author=user, email=f'{username}@test.com')
    return user, author


def make_category(name='Test Category', slug=None):
    cat = Catagory.objects.create(name=name, slug=slug or name.lower().replace(' ', '-'))
    return cat


def make_post(author, catagory, title='Test Post', status='active', visible=True, **kwargs):
    return Blog.objects.create(
        author=author,
        catagories=catagory,
        title=title,
        detail='Detail text',
        status=status,
        visible=visible,
        **kwargs
    )


class BlogModelsTest(TestCase):
    def setUp(self):
        _, self.author = make_author()
        self.cat = make_category()

    def test_like_unique_together(self):
        post = make_post(self.author, self.cat)
        Like.objects.create(post=post, author=self.author, reaction='like')
        with self.assertRaises(IntegrityError):
            Like.objects.create(post=post, author=self.author, reaction='love')

    def test_post_view_unique_together(self):
        post = make_post(self.author, self.cat)
        today = timezone.now().date()
        PostView.objects.create(post=post, date=today, views=1)
        pv, created = PostView.objects.get_or_create(post=post, date=today, defaults={'views': 0})
        self.assertFalse(created)
        self.assertEqual(PostView.objects.filter(post=post, date=today).count(), 1)

    def test_post_first_view_unique_together(self):
        post = make_post(self.author, self.cat)
        user = self.author.author
        PostFirstView.objects.create(post=post, user=user)
        pfv, created = PostFirstView.objects.get_or_create(post=post, user=user)
        self.assertFalse(created)

    def test_views_last_7_days(self):
        post = make_post(self.author, self.cat)
        today = timezone.now().date()
        PostView.objects.create(post=post, date=today, views=5)
        PostView.objects.create(post=post, date=today - timedelta(days=2), views=3)
        self.assertEqual(post.views_last_7_days, 8)


class ContextProcessorTest(TestCase):
    def test_ensure_category_slugs_fills_empty_slug(self):
        cat = Catagory.objects.create(name='Hello World', slug=None)
        _ensure_category_slugs()
        cat.refresh_from_db()
        self.assertEqual(cat.slug, 'hello-world')

    def test_global_variable_returns_category_context(self):
        make_category('Cat A')
        req = type('Req', (), {'session': {}, 'user': None})()
        ctx = globalVariable(req)
        self.assertIn('category', ctx)
        self.assertIn('cat_count', ctx)


class SingleBlogViewCountTest(TestCase):
    def setUp(self):
        _, self.author = make_author()
        self.cat = make_category()
        self.post = make_post(self.author, self.cat)

    def test_anonymous_first_view_increments_count(self):
        c = Client()
        url = reverse('single_blog', args=[self.post.id])
        self.assertEqual(self.post.visit_count, 0)
        c.get(url)
        self.post.refresh_from_db()
        self.assertEqual(self.post.visit_count, 1)

    def test_anonymous_second_view_does_not_increment(self):
        c = Client()
        url = reverse('single_blog', args=[self.post.id])
        c.get(url)
        c.get(url)
        self.post.refresh_from_db()
        self.assertEqual(self.post.visit_count, 1)

    def test_partial_param_does_not_increment(self):
        c = Client()
        url = reverse('single_blog', args=[self.post.id]) + '?partial=1'
        c.get(url)
        self.post.refresh_from_db()
        self.assertEqual(self.post.visit_count, 0)

    def test_author_view_does_not_increment(self):
        c = Client()
        c.force_login(self.author.author)
        url = reverse('single_blog', args=[self.post.id])
        c.get(url)
        self.post.refresh_from_db()
        self.assertEqual(self.post.visit_count, 0)

    def test_other_user_view_increments(self):
        _, other_author = make_author('other')
        c = Client()
        c.force_login(other_author.author)
        url = reverse('single_blog', args=[self.post.id])
        c.get(url)
        self.post.refresh_from_db()
        self.assertEqual(self.post.visit_count, 1)

    def test_draft_returns_404_for_anonymous(self):
        self.post.status = 'draft'
        self.post.save()
        c = Client()
        url = reverse('single_blog', args=[self.post.id])
        resp = c.get(url)
        self.assertEqual(resp.status_code, 404)


class AuthorProfileViewTest(TestCase):
    def setUp(self):
        _, self.author = make_author('writer')
        self.cat = make_category()
        make_post(self.author, self.cat, title='Post 1')

    def test_author_profile_200_and_context(self):
        c = Client()
        url = reverse('author_profile', args=[self.author.author.username])
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['author_profile'], self.author)
        self.assertEqual(resp.context['posts'].count(), 1)
        self.assertIn('total_views', resp.context)

    def test_author_profile_404_unknown_username(self):
        c = Client()
        url = reverse('author_profile', args=['nonexistent'])
        resp = c.get(url)
        self.assertEqual(resp.status_code, 404)


class LikeToggleViewTest(TestCase):
    def setUp(self):
        _, self.author = make_author('owner')
        self.cat = make_category()
        self.post = make_post(self.author, self.cat)
        _, self.other = make_author('other')

    def test_like_requires_login(self):
        c = Client()
        url = reverse('like', args=[self.post.id])
        resp = c.post(url, {})
        self.assertEqual(resp.status_code, 403)

    def test_cannot_like_own_post(self):
        c = Client()
        c.force_login(self.author.author)
        url = reverse('like', args=[self.post.id])
        resp = c.post(url, {'reaction': 'like'})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn('own post', data.get('error', '').lower())

    def test_other_author_can_like(self):
        c = Client()
        c.force_login(self.other.author)
        url = reverse('like', args=[self.post.id])
        resp = c.post(url, {'reaction': 'like'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['liked'])
        self.assertEqual(data['likes_count'], 1)

    def test_like_then_same_reaction_removes(self):
        c = Client()
        c.force_login(self.other.author)
        url = reverse('like', args=[self.post.id])
        c.post(url, {'reaction': 'like'})
        resp = c.post(url, {'reaction': 'like'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['liked'])
        self.assertEqual(data['likes_count'], 0)

    def test_cannot_like_draft_post(self):
        self.post.status = 'draft'
        self.post.save()
        c = Client()
        c.force_login(self.other.author)
        url = reverse('like', args=[self.post.id])
        resp = c.post(url, {'reaction': 'like'})
        self.assertEqual(resp.status_code, 400)


class CatagoryViewTest(TestCase):
    def setUp(self):
        _, self.author = make_author()
        self.cat = make_category('Tech', slug='tech')
        make_post(self.author, self.cat)

    def test_category_by_slug_200(self):
        c = Client()
        url = reverse('catagory', args=['tech'])
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['catagory'], self.cat)

    def test_category_404_invalid_slug(self):
        c = Client()
        url = reverse('catagory', args=['nonexistent-slug'])
        resp = c.get(url)
        self.assertEqual(resp.status_code, 404)
