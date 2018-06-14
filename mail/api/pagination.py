from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination as DefaultPageNumberPagination


class PageNumberPagination(DefaultPageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'