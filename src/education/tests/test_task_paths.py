"""패키지 분리 전 Q2의 문자열 경로와 직렬화한 task 함수가 계속 해석되는지 검사한다."""

import pickle

from django.test import SimpleTestCase
from django.utils.module_loading import import_string

from education.tasks.media import delete_unreferenced_education_image
from education.tasks.reminders import (
    enqueue_consultation_reminder_emails,
    send_consultation_reminder_email,
)


class TaskPathCompatibilityTests(SimpleTestCase):
    def test_original_task_paths_and_pickled_functions_resolve(self):
        for task in (
            enqueue_consultation_reminder_emails,
            send_consultation_reminder_email,
            delete_unreferenced_education_image,
        ):
            with self.subTest(task=task.__name__):
                self.assertIs(import_string(f"education.tasks.{task.__name__}"), task)
                # 이전 모듈 경로로 저장된 함수의 pickle GLOBAL 참조를 재현한다.
                legacy_reference = f"ceducation.tasks\n{task.__name__}\n.".encode()
                self.assertIs(pickle.loads(legacy_reference), task)
