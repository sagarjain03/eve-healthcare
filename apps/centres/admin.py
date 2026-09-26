from django.contrib import admin

from .models import CentreTest, DiagnosticCentre, DiagnosticTest


class CentreTestInline(admin.TabularInline):
    model = CentreTest
    extra = 0
    autocomplete_fields = ("test",)


@admin.register(DiagnosticCentre)
class DiagnosticCentreAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "pincode", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("name", "city")
    inlines = (CentreTestInline,)


@admin.register(DiagnosticTest)
class DiagnosticTestAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sample_type", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(CentreTest)
class CentreTestAdmin(admin.ModelAdmin):
    list_display = ("centre", "test", "price", "is_active")
    list_filter = ("is_active", "centre__city")
    search_fields = ("centre__name", "test__code", "test__name")
    list_select_related = ("centre", "test")
