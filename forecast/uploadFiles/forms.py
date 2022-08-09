from django import forms
from .models import  DataSccModel


class UploadDataFileForm(forms.ModelForm):
    hidden_upload_field = forms.BooleanField(widget=forms.HiddenInput, initial=True)
    class Meta:
        model = DataSccModel
        fields = ( 'excelFile',)





class ForecastForm(forms.Form):
    hidden_forecat_field = forms.BooleanField(widget=forms.HiddenInput, initial=True)