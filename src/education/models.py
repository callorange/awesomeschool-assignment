from django.db import models


class Education(models.Model):
    """공개 교육 소개와 저장소에 독립적인 대표 이미지 참조를 보관한다.

    goals와 audiences는 문자열 목록이다. curriculum은 periods(시수)와
    lessons(교시 목록)으로 구성하며, 각 교시는 period·topic·activity·description을
    가진다. 이 JSON 구조의 입력 검증은 프리셋 명령이 담당한다.
    image는 저장소 상대 이름으로 보관하고 실제 제공 URL은 선택한 Storage가 만든다.
    """

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=100)
    summary = models.CharField(max_length=300)
    image = models.FileField(upload_to="education/", max_length=255)
    image_alt = models.CharField(max_length=200)
    goals = models.JSONField(default=list)
    audiences = models.JSONField(default=list)
    curriculum = models.JSONField(default=list)
    source_url = models.URLField()
    source_image_url = models.URLField(max_length=500)
    collected_on = models.DateField()
    editorial_note = models.TextField()
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "slug"]

    def __str__(self):
        return self.title
