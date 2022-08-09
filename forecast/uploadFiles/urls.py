from django.urls import path

from .views import UploadDataFileView, forecastDataView
from django.contrib.auth.decorators import login_required

urlpatterns = [
path('', login_required(UploadDataFileView), name ='UploadDataFileView'),
    path('forecast',forecastDataView,name="forecastDataView")
    ]