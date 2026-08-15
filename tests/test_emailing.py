import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from inventory_manager import emailing


class FakeReportFile:
    def __init__(self, content: bytes):
        self.content = content
        self.open = Mock()
        self.close = Mock()

    def __bool__(self):
        return True

    def read(self):
        return self.content


class EmailingTests(unittest.TestCase):
    def test_recipient_validation(self) -> None:
        self.assertEqual(
            emailing.normalize_recipient(" dad@example.com "),
            "dad@example.com",
        )

        for value in ("", "not-an-email", "dad@example"):
            with self.subTest(value=value), self.assertRaises(
                emailing.ReportEmailError
            ):
                emailing.normalize_recipient(value)

        self.assertEqual(
            emailing.normalize_recipient(
                "dad@example.com; accounts@example.com, DAD@example.com"
            ),
            "dad@example.com, accounts@example.com",
        )

    def test_generated_pdf_is_attached_and_sent(self) -> None:
        report_file = FakeReportFile(b"%PDF-test")
        output = SimpleNamespace(output=report_file, complete=True, errors=None)
        message = SimpleNamespace(attach=Mock(), send=Mock(return_value=1))
        email_message = Mock(return_value=message)

        django_package = ModuleType("django")
        django_conf = ModuleType("django.conf")
        django_conf.settings = SimpleNamespace(
            DEFAULT_FROM_EMAIL="inventree@example.com"
        )
        django_core = ModuleType("django.core")
        django_mail = ModuleType("django.core.mail")
        django_mail.EmailMessage = email_message

        modules = {
            "django": django_package,
            "django.conf": django_conf,
            "django.core": django_core,
            "django.core.mail": django_mail,
        }

        with (
            patch.dict(sys.modules, modules),
            patch.object(emailing, "email_delivery_available", return_value=True),
        ):
            sent = emailing.send_replenishment_report_email(
                output,
                "dad@example.com, accounts@example.com",
                "Weekly Stock Report",
                b"Part,Quantity\r\nWidget,4\r\n",
            )

        self.assertEqual(sent, 1)
        report_file.open.assert_called_once_with("rb")
        report_file.close.assert_called_once_with()
        email_message.assert_called_once_with(
            subject="Weekly Stock Report",
            body=(
                "Attached is the current Inventory Replenishment Report.\n\n"
                "INTERNAL - DiCor Engineering"
            ),
            from_email="inventree@example.com",
            to=["dad@example.com", "accounts@example.com"],
        )
        pdf_attachment = message.attach.call_args_list[0].args
        csv_attachment = message.attach.call_args_list[1].args
        self.assertTrue(pdf_attachment[0].startswith("inventory-replenishment-"))
        self.assertEqual(pdf_attachment[1:], (b"%PDF-test", "application/pdf"))
        self.assertTrue(csv_attachment[0].endswith(".csv"))
        self.assertEqual(csv_attachment[2], "text/csv")
        message.send.assert_called_once_with(fail_silently=False)

    def test_manual_delivery_is_queued_on_inventree_worker(self) -> None:
        offload_task = Mock(return_value="task-id")
        inventree_package = ModuleType("InvenTree")
        inventree_tasks = ModuleType("InvenTree.tasks")
        inventree_tasks.offload_task = offload_task

        with (
            patch.dict(
                sys.modules,
                {
                    "InvenTree": inventree_package,
                    "InvenTree.tasks": inventree_tasks,
                },
            ),
            patch.object(emailing, "email_delivery_available", return_value=True),
        ):
            task_id = emailing.queue_replenishment_report_email(
                "inventory-manager",
                "dad@example.com",
            )

        self.assertEqual(task_id, "task-id")
        offload_task.assert_called_once_with(
            "plugin.registry.call_plugin_function",
            "inventory-manager",
            "send_configured_report_email",
            group="inventory-manager-email",
        )

    def test_zero_messages_sent_is_a_delivery_failure(self) -> None:
        report_file = FakeReportFile(b"%PDF-test")
        output = SimpleNamespace(
            output=report_file,
            complete=True,
            errors=None,
        )
        message = SimpleNamespace(attach=Mock(), send=Mock(return_value=0))

        django_package = ModuleType("django")
        django_conf = ModuleType("django.conf")
        django_conf.settings = SimpleNamespace(
            DEFAULT_FROM_EMAIL="inventree@example.com"
        )
        django_core = ModuleType("django.core")
        django_mail = ModuleType("django.core.mail")
        django_mail.EmailMessage = Mock(return_value=message)

        with (
            patch.dict(
                sys.modules,
                {
                    "django": django_package,
                    "django.conf": django_conf,
                    "django.core": django_core,
                    "django.core.mail": django_mail,
                },
            ),
            patch.object(emailing, "email_delivery_available", return_value=True),
            self.assertRaises(emailing.ReportEmailError),
        ):
            emailing.send_replenishment_report_email(
                output,
                "dad@example.com",
            )

    def test_incomplete_report_is_not_emailed(self) -> None:
        report_file = FakeReportFile(b"%PDF-test")
        output = SimpleNamespace(
            output=report_file,
            complete=False,
            errors=None,
        )

        with self.assertRaises(emailing.ReportEmailError):
            emailing._read_report_pdf(output)

        report_file.open.assert_not_called()

    def test_failed_queue_is_reported(self) -> None:
        offload_task = Mock(return_value=False)
        inventree_package = ModuleType("InvenTree")
        inventree_tasks = ModuleType("InvenTree.tasks")
        inventree_tasks.offload_task = offload_task

        with (
            patch.dict(
                sys.modules,
                {
                    "InvenTree": inventree_package,
                    "InvenTree.tasks": inventree_tasks,
                },
            ),
            patch.object(emailing, "email_delivery_available", return_value=True),
            self.assertRaises(emailing.ReportEmailError),
        ):
            emailing.queue_replenishment_report_email(
                "inventory-manager",
                "dad@example.com",
            )

    def test_generation_happens_before_delivery(self) -> None:
        output = object()

        with (
            patch.object(
                emailing,
                "generate_replenishment_report",
                return_value=output,
            ) as generate,
            patch.object(emailing, "send_replenishment_report_email") as send,
        ):
            result = emailing.generate_and_email_replenishment_report(
                "dad@example.com"
            )

        self.assertIs(result, output)
        generate.assert_called_once_with()
        send.assert_called_once_with(
            output,
            "dad@example.com",
            emailing.DEFAULT_EMAIL_SUBJECT,
            None,
        )


if __name__ == "__main__":
    unittest.main()
