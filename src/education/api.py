"""익명 신청 생성과 교육 조회만 공개하며 신청 데이터 조회는 제공하지 않는다."""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.generics import CreateAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Education, EducationApplication
from .serializers import EducationApplicationSerializer, EducationSerializer


class EducationDetailAPI(RetrieveAPIView):
    """접수 중단 여부와 무관하게 slug로 공개 교육 안내를 조회한다."""

    queryset = Education.objects.all()
    serializer_class = EducationSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "slug"


@method_decorator(csrf_protect, name="dispatch")
class EducationApplicationCreateAPI(CreateAPIView):
    """인증 여부와 무관하게 CSRF를 검사하고 동일 제출에 200을 반환한다."""

    serializer_class = EducationApplicationSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        """신규 201·동일 제출 200에 식별자와 최초 접수 상태만 반환한다.

        관리자 정정 후 재요청해도 현재 상담 상태나 개인정보를 공개하지 않고
        최초 제출의 접수 확인 응답을 유지한다.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        application = serializer.instance
        return Response(
            {
                "request_id": str(application.request_id),
                "status": EducationApplication.Status.RECEIVED,
                "status_display": EducationApplication.Status.RECEIVED.label,
            },
            status=201 if serializer.created else 200,
        )
