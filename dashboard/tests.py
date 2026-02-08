from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from dashboard.models import Author
from blog.models import Blog, Catagory, Comment


def make_author(username='author1', is_staff=False, **kwargs):
    user = User.objects.create_user(
        username=username, password='testpass123', is_staff=is_staff, **kwargs
    )
    author = Author.objects.create(author=user, email=f'{username}@test.com')
    return user, author


def make_category(name='Test Category'):
    return Catagory.objects.create(name=name, slug=name.lower().replace(' ', '-'))


def make_post(author, category, title='Test Post', status='draft'):
    return Blog.objects.create(
        author=author,
        catagories=category,
        title=title,
        detail='Detail',
        status=status,
        visible=True,
    )


class SubmitPostForReviewTest(TestCase):
    def setUp(self):
        self.user, self.author = make_author()
        self.cat = make_category()
        self.post = make_post(self.author, self.cat, status='draft')

    def test_author_can_submit_for_review(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('post_submit_for_review', args=[str(self.post.id)])
        resp = c.post(url, {})
        self.assertIn(resp.status_code, (200, 302))
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'pending')

    def test_other_user_cannot_submit(self):
        other_user, _ = make_author('other')
        c = Client()
        c.force_login(other_user)
        url = reverse('post_submit_for_review', args=[str(self.post.id)])
        resp = c.post(url, {})
        self.assertIn(resp.status_code, (200, 302))
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'draft')


class PublishPostTest(TestCase):
    def setUp(self):
        self.user, self.author = make_author()
        self.staff_user, _ = make_author('staff', is_staff=True)
        self.cat = make_category()
        self.post = make_post(self.author, self.cat, status='pending')

    def test_staff_can_publish(self):
        c = Client()
        c.force_login(self.staff_user)
        url = reverse('post_publish', args=[str(self.post.id)])
        resp = c.post(url, {})
        self.assertIn(resp.status_code, (200, 302))
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'active')

    def test_author_cannot_publish(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('post_publish', args=[str(self.post.id)])
        resp = c.post(url, {})
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'pending')


class ReturnPostToDraftTest(TestCase):
    def setUp(self):
        self.staff_user, _ = make_author('staff', is_staff=True)
        self.user, self.author = make_author()
        self.cat = make_category()
        self.post = make_post(self.author, self.cat, status='pending')

    def test_staff_can_return_to_draft(self):
        c = Client()
        c.force_login(self.staff_user)
        url = reverse('post_return_to_draft', args=[str(self.post.id)])
        resp = c.post(url, {})
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'draft')

    def test_author_cannot_return_to_draft(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('post_return_to_draft', args=[str(self.post.id)])
        c.post(url, {})
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'pending')


class PendingCommentsViewTest(TestCase):
    def setUp(self):
        self.user, self.author = make_author()
        self.cat = make_category()
        self.post = make_post(self.author, self.cat, status='active')
        self.comment = Comment.objects.create(
            post=self.post, name='visitor', body='Hello', is_approved=False
        )

    def test_pending_comments_requires_login(self):
        c = Client()
        url = reverse('comments_pending')
        resp = c.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_pending_comments_200_for_author(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('comments_pending')
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('comments', resp.context)


class ApproveCommentViewTest(TestCase):
    def setUp(self):
        self.user, self.author = make_author()
        self.cat = make_category()
        self.post = make_post(self.author, self.cat, status='active')
        self.comment = Comment.objects.create(
            post=self.post, name='visitor', body='Hi', is_approved=False
        )

    def test_author_can_approve_comment(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('comment_approve', args=[self.comment.id])
        resp = c.post(url, {})
        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_approved)


class DeleteCommentViewTest(TestCase):
    def setUp(self):
        self.user, self.author = make_author()
        self.cat = make_category()
        self.post = make_post(self.author, self.cat, status='active')
        self.comment = Comment.objects.create(
            post=self.post, name='visitor', body='Hi', is_approved=False
        )

    def test_author_can_delete_comment(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('comment_delete', args=[self.comment.id])
        c.post(url, {})
        self.assertFalse(Comment.objects.filter(id=self.comment.id).exists())


class ChangePasswordViewTest(TestCase):
    def setUp(self):
        self.user, _ = make_author()

    def test_change_password_get_200(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('change_password')
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_change_password_success(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('change_password')
        resp = c.post(url, {
            'current_password': 'testpass123',
            'new_password1': 'newpass123',
            'new_password2': 'newpass123',
        })
        self.assertIn(resp.status_code, (200, 302))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass123'))

    def test_change_password_wrong_current_fails(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('change_password')
        resp = c.post(url, {
            'current_password': 'wrong',
            'new_password1': 'newpass123',
            'new_password2': 'newpass123',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('newpass123'))


class AnalyticsViewTest(TestCase):
    def setUp(self):
        self.user, self.author = make_author()
        self.cat = make_category()
        make_post(self.author, self.cat, status='active', title='My Post')

    def test_analytics_redirects_if_no_author_profile(self):
        user_no_author = User.objects.create_user('noauthor', password='testpass123')
        # User has no Author profile (never created)
        c = Client()
        c.force_login(user_no_author)
        url = reverse('analytics')
        resp = c.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('profile', resp.url)

    def test_analytics_200_for_author(self):
        c = Client()
        c.force_login(self.user)
        url = reverse('analytics')
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('posts_data', resp.context)
