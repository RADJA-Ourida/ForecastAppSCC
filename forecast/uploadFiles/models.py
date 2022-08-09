from django.db import models

# Create your models here.


class DataSccModel(models.Model):
    title = models.CharField(max_length=80)
    excelFile = models.FileField(upload_to='static/documents/')

    class Meta:
        ordering = ['title']

    def __str__(self):
        return f"{self.title}"
