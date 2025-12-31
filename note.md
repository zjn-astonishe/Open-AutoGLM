`emulator.exe -avd AndroidWorld -no-snapshot -grpc 8554`
`ssh -NL 8001:localhost:8001 smc-gpu66 -f`
`python scripts/check_deployment_en.py --base-url http://localhost:8001/v1 --apikey qwerasdfzxcv123 --model qwen3-vl-8B-instruct`
`set an alarm at 12:30 pm every Friday and Sunday, disable the vibration`
`add a clock which shows the New York time`

`pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/` 