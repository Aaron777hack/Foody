

from django.urls import reverse, resolve
from django.test import SimpleTestCase
from core.views import AddProduct 

class TestUrl(SimpleTestCase):

    def test_list_is_resolved(self):
        url = reverse('addProduct')
        self.assertEquals(resolve(url).func.view_class, AddProduct)
