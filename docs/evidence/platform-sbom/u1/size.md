# U1 round 2 image sizes (developer, 2026-10-22)
Method as U0: `docker images` size, and `docker save <image> | wc -c` (what bundle.sh saves). Docker on the Windows host.
- before (U0, 31bfed4): 259 MB image; tar 58,818,048 B.
- after (ke-app:bundle-31bfed4b6a11, build of this working tree): 238 MB image (docker image inspect 54,855,047 B); tar 54,872,576 B.
- change: tar -3,945,472 B (-6.7%).
