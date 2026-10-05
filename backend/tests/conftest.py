def pytest_addoption(parser):
    parser.addoption(
        "--perf", action="store_true", help="run the 1.4M-row import performance test"
    )
