from django.db import models

# Create your models here.
class Users(models.Model):
    user_name = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.username