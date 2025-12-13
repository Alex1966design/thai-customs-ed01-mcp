import os
from app import build_app


def main():
    # Railway sets PORT automatically
    port = int(os.getenv("PORT", "7860"))

    print(f"Starting Thai Customs ED01 app on port {port}")

    demo = build_app()

    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,          # share=True не нужен в Railway
        show_error=True,      # важно: покажет ошибку в UI
        debug=True,           # больше логов в консоли Railway
    )


if __name__ == "__main__":
    main()
