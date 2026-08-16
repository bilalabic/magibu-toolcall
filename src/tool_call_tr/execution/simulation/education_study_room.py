"""Stateful simulator for university study-room reservations."""

from __future__ import annotations

from typing import Any

from tool_call_tr.execution.simulation import SimulationTool


class StudyRoomReservationTool:
    """Simulates a resettable university study-room reservation system."""

    function_names = ("education_book_study_room",)

    def initial_state(self) -> dict[str, Any]:
        return {
            "rooms": {
                "study_a101": {
                    "name": "A101 Çalışma Odası",
                    "capacity": 4,
                },
                "study_b201": {
                    "name": "B201 Çalışma Odası",
                    "capacity": 8,
                },
                "study_c301": {
                    "name": "C301 Çalışma Odası",
                    "capacity": 6,
                },
            },
            "reservations": [
                {
                    "reservation_id": "reservation_001",
                    "room_id": "study_a101",
                    "date": "2026-09-17",
                    "start_time": "14:00",
                    "end_time": "15:00",
                    "attendee_count": 2,
                    "status": "confirmed",
                }
            ],
            "next_reservation_number": 2,
        }

    def execute(
        self,
        state: dict[str, Any],
        function_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if function_name != "education_book_study_room":
            raise ValueError(f"Unsupported function: {function_name}")

        room_id = arguments["room_id"]
        date = arguments["date"]
        start_time = arguments["start_time"]
        end_time = arguments["end_time"]
        attendee_count = arguments["attendee_count"]
        confirmed = arguments["confirmed"]

        room = state["rooms"].get(room_id)

        if room is None:
            return self._result(
                status="invalid_request",
                available=False,
                message="Belirtilen çalışma odası bulunamadı.",
            )

        if end_time <= start_time:
            return self._result(
                status="invalid_request",
                available=False,
                message="Bitiş saati başlangıç saatinden sonra olmalıdır.",
            )

        if attendee_count > room["capacity"]:
            return self._result(
                status="capacity_exceeded",
                available=False,
                message=(
                    f"{room_id} odasının kapasitesi {room['capacity']} kişidir."
                ),
            )

        conflicting_reservation = self._find_conflict(
            state=state,
            room_id=room_id,
            date=date,
            start_time=start_time,
            end_time=end_time,
        )

        if conflicting_reservation is not None:
            return self._result(
                status="conflict",
                available=False,
                conflict_with=conflicting_reservation["reservation_id"],
                message="Seçilen oda belirtilen saat aralığında müsait değildir.",
            )

        if not confirmed:
            return self._result(
                status="confirmation_required",
                available=True,
                confirmation_required=True,
                message=(
                    "Oda belirtilen saat aralığında uygundur. "
                    "Rezervasyon oluşturulmadan önce kullanıcı onayı gereklidir."
                ),
            )

        reservation_number = state["next_reservation_number"]
        reservation_id = f"reservation_{reservation_number:03d}"

        reservation = {
            "reservation_id": reservation_id,
            "room_id": room_id,
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "attendee_count": attendee_count,
            "status": "confirmed",
        }

        state["reservations"].append(reservation)
        state["next_reservation_number"] += 1

        return self._result(
            status="confirmed",
            available=True,
            reservation_id=reservation_id,
            message="Çalışma odası rezervasyonu başarıyla oluşturuldu.",
        )

    @staticmethod
    def _find_conflict(
        state: dict[str, Any],
        room_id: str,
        date: str,
        start_time: str,
        end_time: str,
    ) -> dict[str, Any] | None:
        for reservation in state["reservations"]:
            if reservation["status"] != "confirmed":
                continue

            if reservation["room_id"] != room_id:
                continue

            if reservation["date"] != date:
                continue

            existing_start = reservation["start_time"]
            existing_end = reservation["end_time"]

            overlaps = start_time < existing_end and end_time > existing_start

            if overlaps:
                return reservation

        return None

    @staticmethod
    def _result(
        *,
        status: str,
        available: bool,
        reservation_id: str | None = None,
        confirmation_required: bool = False,
        conflict_with: str | None = None,
        message: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "available": available,
            "reservation_id": reservation_id,
            "confirmation_required": confirmation_required,
            "conflict_with": conflict_with,
            "message": message,
        }


TOOLS: tuple[SimulationTool, ...] = (
    StudyRoomReservationTool(),
)
