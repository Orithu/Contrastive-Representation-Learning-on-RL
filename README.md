Contrastive Representation Learning on RL
=======
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)

**Status**: Archive (code is provided as-is, no updates expected)

This is an implementation of contrastive Representation Learning using on Reinforcement Learning. Base code forked from [curl-rainbow](https://github.com/aravindsrinivas/curl_rainbow) for Atari
games. The code by default uses the 100k timesteps benchmark and has not been
tested for any other setting.

Run the following command (or `bash run_curl.sh`) with the game as an argument:

```
python3 main.py --game ms_pacman

# to use moco contrastive method, run the following command
python3 main.py --game ms_pacman --contrastive moco

# to use SimSiam contrastive method, run the following command
python3 main.py --game ms_pacman --contrastive simsiam
```

To install all dependencies, run `bash install.sh`.

## References

  - [PatrickHua/SimSiam](https://github.com/PatrickHua/SimSiam/blob/main/models/simsiam.py)