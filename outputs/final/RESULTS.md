# Final results (Task 3)

Built by `scripts/13_final_results.py report` from `outputs/final/raw/`. 20 demand scenarios, UE gap 0.0001, AM and PM peak, demand x1, x1.3, x1.6.
Change = new / today - 1 in total system travel time (TSTT), per scenario; negative = faster. AM+PM adds the two peaks of the same scenario.

## 1. Noise floor

Largest per-scenario difference between two solves of the same network at gap 0.0001 (edge order shuffled): **0.0145%**; largest difference between gap 0.0001 and 1e-05: **0.0429%**. Detection threshold used below: **0.10%** (config.MIN_MEAN_IMPROVEMENT), and a result also needs the same sign in at least 80% of scenarios.

| demand | peak | compare | n | median_abs | p95_abs | max_abs | iterations |
|---|---|---|---|---|---|---|---|
| 1 | am | shuffle1 vs canonical | 20 | +0.000% | +0.002% | +0.004% | 17 |
| 1 | am | shuffle2 vs canonical | 20 | +0.000% | +0.002% | +0.003% | 17 |
| 1 | am | tight vs canonical | 20 | +0.004% | +0.010% | +0.014% | 54 |
| 1 | pm | shuffle1 vs canonical | 20 | +0.000% | +0.000% | +0.005% | 19 |
| 1 | pm | shuffle2 vs canonical | 20 | +0.000% | +0.010% | +0.014% | 19 |
| 1 | pm | tight vs canonical | 20 | +0.009% | +0.025% | +0.030% | 51 |
| 1.3 | am | shuffle1 vs canonical | 20 | +0.000% | +0.003% | +0.006% | 31 |
| 1.3 | am | shuffle2 vs canonical | 20 | +0.000% | +0.007% | +0.011% | 31 |
| 1.3 | am | tight vs canonical | 20 | +0.006% | +0.019% | +0.022% | 120 |
| 1.3 | pm | shuffle1 vs canonical | 20 | +0.000% | +0.001% | +0.014% | 38 |
| 1.3 | pm | shuffle2 vs canonical | 20 | +0.000% | +0.003% | +0.003% | 38 |
| 1.3 | pm | tight vs canonical | 20 | +0.007% | +0.024% | +0.043% | 141 |
| 1.6 | am | shuffle1 vs canonical | 20 | +0.000% | +0.006% | +0.008% | 42 |
| 1.6 | am | shuffle2 vs canonical | 20 | +0.000% | +0.006% | +0.008% | 42 |
| 1.6 | am | tight vs canonical | 20 | +0.007% | +0.020% | +0.020% | 163 |
| 1.6 | pm | shuffle1 vs canonical | 20 | +0.000% | +0.000% | +0.005% | 56 |
| 1.6 | pm | shuffle2 vs canonical | 20 | +0.000% | +0.000% | +0.005% | 56 |
| 1.6 | pm | tight vs canonical | 20 | +0.007% | +0.016% | +0.020% | 278 |
| 1 | am+pm | shuffle1 vs canonical | 20 | +0.000% | +0.002% | +0.003% |  |
| 1 | am+pm | shuffle2 vs canonical | 20 | +0.000% | +0.005% | +0.007% |  |
| 1 | am+pm | tight vs canonical | 20 | +0.002% | +0.013% | +0.016% |  |
| 1.3 | am+pm | shuffle1 vs canonical | 20 | +0.000% | +0.002% | +0.010% |  |
| 1.3 | am+pm | shuffle2 vs canonical | 20 | +0.000% | +0.003% | +0.004% |  |
| 1.3 | am+pm | tight vs canonical | 20 | +0.006% | +0.015% | +0.021% |  |
| 1.6 | am+pm | shuffle1 vs canonical | 20 | +0.000% | +0.003% | +0.003% |  |
| 1.6 | am+pm | shuffle2 vs canonical | 20 | +0.000% | +0.001% | +0.003% |  |
| 1.6 | am+pm | tight vs canonical | 20 | +0.007% | +0.013% | +0.013% |  |

## 2. Back-test: Spring/Cannon two-way (today) vs one-way (2016)

| bonus | demand | peak | n | mean | p10 | median | p90 | improved_share | vkm_mean | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.1 | 1 | am | 20 | -0.154% | -0.179% | -0.158% | -0.134% | 100% | -0.099% | detectable: better |
| 1.1 | 1 | pm | 20 | -0.157% | -0.188% | -0.158% | -0.116% | 100% | -0.109% | detectable: better |
| 1.1 | 1 | am+pm | 20 | -0.156% | -0.172% | -0.159% | -0.122% | 100% | -0.104% | detectable: better |
| 1.1 | 1.3 | am | 20 | -0.137% | -0.160% | -0.140% | -0.115% | 100% | -0.093% | detectable: better |
| 1.1 | 1.3 | pm | 20 | -0.122% | -0.146% | -0.122% | -0.090% | 100% | -0.116% | detectable: better |
| 1.1 | 1.3 | am+pm | 20 | -0.129% | -0.146% | -0.129% | -0.108% | 100% | -0.105% | detectable: better |
| 1.1 | 1.6 | am | 20 | -0.081% | -0.112% | -0.083% | -0.044% | 95% | -0.101% | not detectable |
| 1.1 | 1.6 | pm | 20 | -0.028% | -0.087% | -0.027% | +0.037% | 80% | -0.120% | not detectable |
| 1.1 | 1.6 | am+pm | 20 | -0.054% | -0.089% | -0.056% | -0.014% | 95% | -0.111% | not detectable |

Modeled two-way volume at the count stations (both directions, median over scenarios, vph; interior count K 0.077 AM / 0.082 PM):

| demand | config | street | am | pm | am_plus_pm |
|---|---|---|---|---|---|
| 1 | after (today) | spring | 823 | 945 | 1775 |
| 1 | after (today) | cannon | 511 | 442 | 965 |
| 1 | before (2016) | spring | 568 | 723 | 1298 |
| 1 | before (2016) | cannon | 591 | 507 | 1103 |
| 1.3 | after (today) | spring | 1135 | 1247 | 2373 |
| 1.3 | after (today) | cannon | 688 | 648 | 1333 |
| 1.3 | before (2016) | spring | 836 | 1035 | 1884 |
| 1.3 | before (2016) | cannon | 887 | 751 | 1639 |
| 1.6 | after (today) | spring | 1375 | 1490 | 2881 |
| 1.6 | after (today) | cannon | 844 | 968 | 1834 |
| 1.6 | before (2016) | spring | 1195 | 1443 | 2664 |
| 1.6 | before (2016) | cannon | 1115 | 1021 | 2136 |

Modeled change vs observed SCDOT AADT change (conversion late 2017):

| demand | street | am_change | pm_change | am_plus_pm_change | observed_2016_to_2018 | observed_2016_to_2019 | observed_2016_to_2025 | sign_matches_all_years |
|---|---|---|---|---|---|---|---|---|
| 1 | cannon | -13.559% | -12.828% | -12.552% | +1.754% | +7.018% | +0.000% | False |
| 1 | spring | +44.865% | +30.745% | +36.783% | -7.463% | -25.373% | -16.418% | False |
| 1.3 | cannon | -22.370% | -13.731% | -18.668% | +1.754% | +7.018% | +0.000% | False |
| 1.3 | spring | +35.863% | +20.491% | +25.967% | -7.463% | -25.373% | -16.418% | False |
| 1.6 | cannon | -24.294% | -5.184% | -14.143% | +1.754% | +7.018% | +0.000% | False |
| 1.6 | spring | +15.078% | +3.235% | +8.157% | -7.463% | -25.373% | -16.418% | False |

## 3. City question (two-way conversions) and the P5-2 Ashley move

| variant | segments_converted |
|---|---|
| Coming Street | 23 |
| Rutledge Avenue | 19 |
| Ashley Avenue | 18 |
| all three | 60 |

8 one-way segment(s) on these streets cannot go two-way (1 lane or frozen): `city_blocked_segments.csv`.

**AM+PM**

| config | bonus | demand | mean | p10 | median | p90 | improved_share | vkm_mean | verdict |
|---|---|---|---|---|---|---|---|---|---|
| Coming Street | 1 | 1 | -0.138% | -0.178% | -0.140% | -0.097% | 100% | -0.170% | detectable: better |
| Rutledge Avenue | 1 | 1 | +0.129% | +0.007% | +0.140% | +0.237% | 10% | -0.082% | detectable: worse |
| Ashley Avenue | 1 | 1 | +0.083% | +0.042% | +0.075% | +0.138% | 0% | -0.026% | not detectable |
| all three | 1 | 1 | -0.132% | -0.202% | -0.139% | -0.039% | 95% | -0.275% | detectable: better |
| Ashley Calhoun-Crosstown | 1 | 1 | +0.043% | +0.000% | +0.036% | +0.102% | 10% | -0.036% | not detectable |
| Coming Street | 1 | 1.3 | -0.135% | -0.177% | -0.140% | -0.091% | 100% | -0.183% | detectable: better |
| Rutledge Avenue | 1 | 1.3 | +0.294% | +0.163% | +0.312% | +0.395% | 0% | -0.078% | detectable: worse |
| Ashley Avenue | 1 | 1.3 | +0.173% | +0.103% | +0.177% | +0.235% | 0% | -0.005% | detectable: worse |
| all three | 1 | 1.3 | -0.005% | -0.074% | -0.001% | +0.071% | 50% | -0.274% | not detectable |
| Ashley Calhoun-Crosstown | 1 | 1.3 | +0.098% | +0.030% | +0.099% | +0.150% | 5% | -0.025% | not detectable |
| Coming Street | 1 | 1.6 | -0.154% | -0.211% | -0.149% | -0.111% | 100% | -0.175% | detectable: better |
| Rutledge Avenue | 1 | 1.6 | +0.395% | +0.212% | +0.442% | +0.538% | 0% | -0.056% | detectable: worse |
| Ashley Avenue | 1 | 1.6 | +0.239% | +0.180% | +0.250% | +0.313% | 0% | +0.021% | detectable: worse |
| all three | 1 | 1.6 | +0.079% | +0.005% | +0.067% | +0.157% | 5% | -0.257% | not detectable |
| Ashley Calhoun-Crosstown | 1 | 1.6 | +0.133% | +0.061% | +0.129% | +0.220% | 5% | -0.010% | detectable: worse |
| Coming Street | 1.1 | 1 | -0.130% | -0.170% | -0.129% | -0.081% | 100% | -0.177% | detectable: better |
| Rutledge Avenue | 1.1 | 1 | +0.145% | +0.033% | +0.161% | +0.253% | 10% | -0.085% | detectable: worse |
| Ashley Avenue | 1.1 | 1 | +0.089% | +0.035% | +0.080% | +0.147% | 0% | -0.028% | not detectable |
| all three | 1.1 | 1 | -0.114% | -0.189% | -0.125% | -0.016% | 90% | -0.280% | detectable: better |
| Ashley Calhoun-Crosstown | 1.1 | 1 | +0.046% | -0.002% | +0.031% | +0.117% | 15% | -0.036% | not detectable |
| Coming Street | 1.1 | 1.3 | -0.112% | -0.140% | -0.112% | -0.074% | 100% | -0.184% | detectable: better |
| Rutledge Avenue | 1.1 | 1.3 | +0.332% | +0.183% | +0.356% | +0.441% | 0% | -0.084% | detectable: worse |
| Ashley Avenue | 1.1 | 1.3 | +0.189% | +0.109% | +0.193% | +0.260% | 0% | -0.007% | detectable: worse |
| all three | 1.1 | 1.3 | +0.066% | -0.020% | +0.062% | +0.158% | 15% | -0.280% | not detectable |
| Ashley Calhoun-Crosstown | 1.1 | 1.3 | +0.112% | +0.027% | +0.114% | +0.193% | 0% | -0.025% | detectable: worse |
| Coming Street | 1.1 | 1.6 | -0.113% | -0.164% | -0.105% | -0.066% | 100% | -0.176% | detectable: better |
| Rutledge Avenue | 1.1 | 1.6 | +0.480% | +0.309% | +0.526% | +0.611% | 0% | -0.057% | detectable: worse |
| Ashley Avenue | 1.1 | 1.6 | +0.282% | +0.197% | +0.294% | +0.382% | 0% | +0.026% | detectable: worse |
| all three | 1.1 | 1.6 | +0.208% | +0.122% | +0.192% | +0.316% | 0% | -0.256% | detectable: worse |
| Ashley Calhoun-Crosstown | 1.1 | 1.6 | +0.170% | +0.078% | +0.167% | +0.271% | 0% | -0.008% | detectable: worse |
| Coming Street | 1.2 | 1 | -0.123% | -0.172% | -0.127% | -0.082% | 100% | -0.178% | detectable: better |
| Rutledge Avenue | 1.2 | 1 | +0.158% | +0.051% | +0.169% | +0.266% | 5% | -0.083% | detectable: worse |
| Ashley Avenue | 1.2 | 1 | +0.097% | +0.039% | +0.079% | +0.171% | 0% | -0.026% | not detectable |
| all three | 1.2 | 1 | -0.098% | -0.180% | -0.106% | +0.014% | 85% | -0.282% | not detectable |
| Ashley Calhoun-Crosstown | 1.2 | 1 | +0.053% | -0.003% | +0.046% | +0.120% | 15% | -0.036% | not detectable |
| Coming Street | 1.2 | 1.3 | -0.088% | -0.117% | -0.094% | -0.047% | 100% | -0.190% | not detectable |
| Rutledge Avenue | 1.2 | 1.3 | +0.357% | +0.192% | +0.381% | +0.470% | 0% | -0.088% | detectable: worse |
| Ashley Avenue | 1.2 | 1.3 | +0.194% | +0.108% | +0.191% | +0.290% | 0% | -0.008% | detectable: worse |
| all three | 1.2 | 1.3 | +0.111% | +0.022% | +0.096% | +0.214% | 5% | -0.285% | detectable: worse |
| Ashley Calhoun-Crosstown | 1.2 | 1.3 | +0.119% | +0.041% | +0.119% | +0.210% | 0% | -0.024% | detectable: worse |
| Coming Street | 1.2 | 1.6 | -0.086% | -0.127% | -0.084% | -0.040% | 100% | -0.177% | not detectable |
| Rutledge Avenue | 1.2 | 1.6 | +0.533% | +0.335% | +0.577% | +0.673% | 0% | -0.058% | detectable: worse |
| Ashley Avenue | 1.2 | 1.6 | +0.310% | +0.194% | +0.304% | +0.401% | 0% | +0.030% | detectable: worse |
| all three | 1.2 | 1.6 | +0.304% | +0.184% | +0.277% | +0.433% | 0% | -0.255% | detectable: worse |
| Ashley Calhoun-Crosstown | 1.2 | 1.6 | +0.191% | +0.075% | +0.192% | +0.295% | 0% | -0.006% | detectable: worse |

**AM**

| config | bonus | demand | mean | p10 | median | p90 | improved_share | vkm_mean | verdict |
|---|---|---|---|---|---|---|---|---|---|
| Coming Street | 1 | 1 | -0.174% | -0.215% | -0.173% | -0.135% | 100% | -0.109% | detectable: better |
| Rutledge Avenue | 1 | 1 | +0.254% | +0.098% | +0.231% | +0.471% | 0% | -0.101% | detectable: worse |
| Ashley Avenue | 1 | 1 | -0.037% | -0.059% | -0.031% | -0.014% | 100% | -0.035% | not detectable |
| all three | 1 | 1 | -0.154% | -0.213% | -0.163% | -0.074% | 100% | -0.224% | detectable: better |
| Ashley Calhoun-Crosstown | 1 | 1 | -0.037% | -0.062% | -0.034% | -0.016% | 95% | -0.036% | not detectable |
| Coming Street | 1 | 1.3 | -0.227% | -0.297% | -0.218% | -0.168% | 100% | -0.146% | detectable: better |
| Rutledge Avenue | 1 | 1.3 | +0.581% | +0.379% | +0.591% | +0.783% | 0% | -0.104% | detectable: worse |
| Ashley Avenue | 1 | 1.3 | -0.074% | -0.182% | -0.057% | -0.003% | 95% | -0.029% | not detectable |
| all three | 1 | 1.3 | -0.040% | -0.098% | -0.041% | +0.017% | 70% | -0.252% | not detectable |
| Ashley Calhoun-Crosstown | 1 | 1.3 | -0.076% | -0.186% | -0.065% | -0.005% | 100% | -0.033% | not detectable |
| Coming Street | 1 | 1.6 | -0.375% | -0.534% | -0.362% | -0.268% | 100% | -0.140% | detectable: better |
| Rutledge Avenue | 1 | 1.6 | +0.931% | +0.658% | +0.952% | +1.269% | 0% | -0.067% | detectable: worse |
| Ashley Avenue | 1 | 1.6 | -0.106% | -0.280% | -0.063% | -0.012% | 90% | -0.024% | detectable: better |
| all three | 1 | 1.6 | -0.051% | -0.127% | -0.042% | -0.000% | 90% | -0.235% | not detectable |
| Ashley Calhoun-Crosstown | 1 | 1.6 | -0.120% | -0.302% | -0.077% | -0.005% | 90% | -0.033% | detectable: better |
| Coming Street | 1.1 | 1 | -0.167% | -0.207% | -0.169% | -0.138% | 100% | -0.113% | detectable: better |
| Rutledge Avenue | 1.1 | 1 | +0.263% | +0.104% | +0.233% | +0.509% | 0% | -0.105% | detectable: worse |
| Ashley Avenue | 1.1 | 1 | -0.032% | -0.050% | -0.028% | -0.008% | 100% | -0.037% | not detectable |
| all three | 1.1 | 1 | -0.143% | -0.226% | -0.162% | -0.051% | 100% | -0.226% | detectable: better |
| Ashley Calhoun-Crosstown | 1.1 | 1 | -0.033% | -0.050% | -0.031% | -0.011% | 100% | -0.036% | not detectable |
| Coming Street | 1.1 | 1.3 | -0.187% | -0.237% | -0.186% | -0.135% | 100% | -0.146% | detectable: better |
| Rutledge Avenue | 1.1 | 1.3 | +0.588% | +0.361% | +0.612% | +0.816% | 0% | -0.109% | detectable: worse |
| Ashley Avenue | 1.1 | 1.3 | -0.047% | -0.158% | -0.028% | +0.003% | 85% | -0.032% | not detectable |
| all three | 1.1 | 1.3 | +0.013% | -0.081% | +0.009% | +0.106% | 45% | -0.255% | not detectable |
| Ashley Calhoun-Crosstown | 1.1 | 1.3 | -0.054% | -0.172% | -0.034% | +0.004% | 85% | -0.036% | not detectable |
| Coming Street | 1.1 | 1.6 | -0.329% | -0.495% | -0.303% | -0.215% | 100% | -0.145% | detectable: better |
| Rutledge Avenue | 1.1 | 1.6 | +0.981% | +0.670% | +0.987% | +1.284% | 0% | -0.078% | detectable: worse |
| Ashley Avenue | 1.1 | 1.6 | -0.094% | -0.237% | -0.071% | +0.030% | 85% | -0.024% | not detectable |
| all three | 1.1 | 1.6 | +0.065% | +0.006% | +0.055% | +0.129% | 5% | -0.245% | not detectable |
| Ashley Calhoun-Crosstown | 1.1 | 1.6 | -0.109% | -0.261% | -0.090% | +0.005% | 85% | -0.031% | detectable: better |
| Coming Street | 1.2 | 1 | -0.158% | -0.204% | -0.160% | -0.119% | 100% | -0.112% | detectable: better |
| Rutledge Avenue | 1.2 | 1 | +0.266% | +0.088% | +0.254% | +0.496% | 0% | -0.105% | detectable: worse |
| Ashley Avenue | 1.2 | 1 | -0.029% | -0.044% | -0.026% | -0.006% | 100% | -0.034% | not detectable |
| all three | 1.2 | 1 | -0.134% | -0.216% | -0.148% | -0.031% | 100% | -0.224% | detectable: better |
| Ashley Calhoun-Crosstown | 1.2 | 1 | -0.031% | -0.049% | -0.029% | -0.007% | 100% | -0.034% | not detectable |
| Coming Street | 1.2 | 1.3 | -0.156% | -0.206% | -0.156% | -0.103% | 100% | -0.153% | detectable: better |
| Rutledge Avenue | 1.2 | 1.3 | +0.594% | +0.361% | +0.600% | +0.818% | 0% | -0.109% | detectable: worse |
| Ashley Avenue | 1.2 | 1.3 | -0.039% | -0.172% | -0.019% | +0.022% | 70% | -0.033% | not detectable |
| all three | 1.2 | 1.3 | +0.039% | -0.060% | +0.040% | +0.129% | 30% | -0.256% | not detectable |
| Ashley Calhoun-Crosstown | 1.2 | 1.3 | -0.043% | -0.173% | -0.024% | +0.011% | 70% | -0.033% | not detectable |
| Coming Street | 1.2 | 1.6 | -0.278% | -0.409% | -0.252% | -0.176% | 100% | -0.144% | detectable: better |
| Rutledge Avenue | 1.2 | 1.6 | +1.003% | +0.691% | +1.017% | +1.329% | 0% | -0.080% | detectable: worse |
| Ashley Avenue | 1.2 | 1.6 | -0.083% | -0.198% | -0.065% | +0.031% | 85% | -0.023% | not detectable |
| all three | 1.2 | 1.6 | +0.155% | +0.073% | +0.158% | +0.238% | 0% | -0.244% | detectable: worse |
| Ashley Calhoun-Crosstown | 1.2 | 1.6 | -0.098% | -0.206% | -0.082% | +0.006% | 85% | -0.030% | not detectable |

**PM**

| config | bonus | demand | mean | p10 | median | p90 | improved_share | vkm_mean | verdict |
|---|---|---|---|---|---|---|---|---|---|
| Coming Street | 1 | 1 | -0.104% | -0.157% | -0.112% | -0.032% | 100% | -0.228% | detectable: better |
| Rutledge Avenue | 1 | 1 | +0.010% | -0.080% | +0.010% | +0.112% | 45% | -0.063% | not detectable |
| Ashley Avenue | 1 | 1 | +0.199% | +0.116% | +0.174% | +0.305% | 0% | -0.017% | detectable: worse |
| all three | 1 | 1 | -0.112% | -0.184% | -0.120% | +0.011% | 85% | -0.324% | detectable: better |
| Ashley Calhoun-Crosstown | 1 | 1 | +0.119% | +0.036% | +0.107% | +0.233% | 0% | -0.035% | detectable: worse |
| Coming Street | 1 | 1.3 | -0.048% | -0.104% | -0.048% | +0.018% | 80% | -0.219% | not detectable |
| Rutledge Avenue | 1 | 1.3 | +0.022% | -0.076% | +0.031% | +0.101% | 25% | -0.053% | not detectable |
| Ashley Avenue | 1 | 1.3 | +0.408% | +0.277% | +0.401% | +0.509% | 0% | +0.018% | detectable: worse |
| all three | 1 | 1.3 | +0.029% | -0.073% | +0.004% | +0.153% | 50% | -0.295% | not detectable |
| Ashley Calhoun-Crosstown | 1 | 1.3 | +0.263% | +0.147% | +0.254% | +0.363% | 0% | -0.017% | detectable: worse |
| Coming Street | 1 | 1.6 | +0.054% | -0.025% | +0.037% | +0.162% | 25% | -0.208% | not detectable |
| Rutledge Avenue | 1 | 1.6 | -0.109% | -0.257% | -0.089% | +0.012% | 80% | -0.045% | detectable: better |
| Ashley Avenue | 1 | 1.6 | +0.564% | +0.432% | +0.545% | +0.695% | 0% | +0.064% | detectable: worse |
| all three | 1 | 1.6 | +0.202% | +0.038% | +0.155% | +0.361% | 5% | -0.278% | detectable: worse |
| Ashley Calhoun-Crosstown | 1 | 1.6 | +0.370% | +0.250% | +0.377% | +0.490% | 0% | +0.012% | detectable: worse |
| Coming Street | 1.1 | 1 | -0.093% | -0.145% | -0.111% | -0.015% | 100% | -0.239% | not detectable |
| Rutledge Avenue | 1.1 | 1 | +0.033% | -0.062% | +0.014% | +0.151% | 35% | -0.065% | not detectable |
| Ashley Avenue | 1.1 | 1 | +0.204% | +0.114% | +0.178% | +0.322% | 0% | -0.018% | detectable: worse |
| all three | 1.1 | 1 | -0.087% | -0.191% | -0.114% | +0.058% | 75% | -0.333% | not detectable |
| Ashley Calhoun-Crosstown | 1.1 | 1 | +0.122% | +0.026% | +0.110% | +0.255% | 0% | -0.036% | detectable: worse |
| Coming Street | 1.1 | 1.3 | -0.040% | -0.083% | -0.034% | +0.001% | 85% | -0.221% | not detectable |
| Rutledge Avenue | 1.1 | 1.3 | +0.088% | +0.005% | +0.110% | +0.156% | 10% | -0.059% | not detectable |
| Ashley Avenue | 1.1 | 1.3 | +0.415% | +0.272% | +0.388% | +0.547% | 0% | +0.018% | detectable: worse |
| all three | 1.1 | 1.3 | +0.117% | +0.005% | +0.111% | +0.223% | 5% | -0.303% | detectable: worse |
| Ashley Calhoun-Crosstown | 1.1 | 1.3 | +0.270% | +0.142% | +0.263% | +0.408% | 0% | -0.014% | detectable: worse |
| Coming Street | 1.1 | 1.6 | +0.091% | -0.013% | +0.070% | +0.200% | 15% | -0.207% | not detectable |
| Rutledge Avenue | 1.1 | 1.6 | +0.007% | -0.138% | +0.042% | +0.104% | 40% | -0.037% | not detectable |
| Ashley Avenue | 1.1 | 1.6 | +0.638% | +0.502% | +0.617% | +0.774% | 0% | +0.075% | detectable: worse |
| all three | 1.1 | 1.6 | +0.344% | +0.183% | +0.332% | +0.535% | 0% | -0.266% | detectable: worse |
| Ashley Calhoun-Crosstown | 1.1 | 1.6 | +0.433% | +0.312% | +0.428% | +0.607% | 0% | +0.015% | detectable: worse |
| Coming Street | 1.2 | 1 | -0.089% | -0.146% | -0.101% | -0.010% | 100% | -0.242% | not detectable |
| Rutledge Avenue | 1.2 | 1 | +0.054% | -0.036% | +0.052% | +0.169% | 25% | -0.063% | not detectable |
| Ashley Avenue | 1.2 | 1 | +0.217% | +0.120% | +0.181% | +0.341% | 0% | -0.018% | detectable: worse |
| all three | 1.2 | 1 | -0.064% | -0.171% | -0.071% | +0.069% | 75% | -0.338% | not detectable |
| Ashley Calhoun-Crosstown | 1.2 | 1 | +0.133% | +0.014% | +0.118% | +0.270% | 0% | -0.038% | detectable: worse |
| Coming Street | 1.2 | 1.3 | -0.023% | -0.090% | -0.027% | +0.045% | 75% | -0.225% | not detectable |
| Rutledge Avenue | 1.2 | 1.3 | +0.131% | +0.046% | +0.147% | +0.207% | 10% | -0.068% | detectable: worse |
| Ashley Avenue | 1.2 | 1.3 | +0.417% | +0.268% | +0.382% | +0.561% | 0% | +0.016% | detectable: worse |
| all three | 1.2 | 1.3 | +0.178% | +0.008% | +0.164% | +0.319% | 5% | -0.313% | detectable: worse |
| Ashley Calhoun-Crosstown | 1.2 | 1.3 | +0.274% | +0.137% | +0.257% | +0.438% | 0% | -0.014% | detectable: worse |
| Coming Street | 1.2 | 1.6 | +0.097% | -0.035% | +0.082% | +0.235% | 15% | -0.209% | not detectable |
| Rutledge Avenue | 1.2 | 1.6 | +0.086% | -0.046% | +0.102% | +0.188% | 20% | -0.038% | not detectable |
| Ashley Avenue | 1.2 | 1.6 | +0.682% | +0.520% | +0.682% | +0.859% | 0% | +0.081% | detectable: worse |
| all three | 1.2 | 1.6 | +0.445% | +0.277% | +0.421% | +0.658% | 0% | -0.265% | detectable: worse |
| Ashley Calhoun-Crosstown | 1.2 | 1.6 | +0.466% | +0.323% | +0.467% | +0.644% | 0% | +0.018% | detectable: worse |

## 4. Open search (09_search.py, AM+PM, 46 corridors)

| demand | rounds | finished | accepted |
|---|---|---|---|
| 1 | 1 | True | none |
| 1.3 | 1 | True | none |
| 1.6 | 1 | True | none |

Screening (3 scenarios, gap 1e-3), round 1, all moves: x1: 86 evaluated, 0 better than -0.1%, 54 within +/-0.1%, 32 worse; x1.3: 86 evaluated, 0 better than -0.1%, 49 within +/-0.1%, 37 worse; x1.6: 86 evaluated, 0 better than -0.1%, 51 within +/-0.1%, 35 worse

Confirmed on all scenarios (AM+PM; only moves better than -0.05% in screening go to confirmation):

| demand | round | name | corridor | mode | confirm_mean | confirm_p10 | confirm_p90 | confirm_win | confirm_accept |
|---|---|---|---|---|---|---|---|---|---|
| 1.6 | 1 | King Street | 9 | fwd | -0.047% | -0.082% | -0.011% | 90% | False |

Pareto front of round-1 single moves (screening numbers; lower TSTT, lower veh-km, higher two-way share):

| demand | name | corridor | mode | d_tstt | d_vkm | d_two_way_share |
|---|---|---|---|---|---|---|
| 1 | Ashley Avenue | 0 | two | +0.046% | -0.017% | +0.572% |
| 1 | Coming Street | 2 | two | +0.071% | -0.012% | +0.736% |
| 1 | Rutledge Avenue | 3 | two | -0.049% | -0.028% | +0.261% |
| 1 | Coming Street | 8 | two | +0.005% | -0.006% | +0.326% |
| 1 | King Street | 9 | fwd | -0.017% | -0.049% | -0.068% |
| 1 | Rutledge Avenue | 12 | two | +0.159% | -0.058% | +0.627% |
| 1 | Morrison Drive | 14 | two | +0.013% | -0.004% | +0.511% |
| 1 | Meeting Street | 25 | two | +0.017% | -0.008% | +0.501% |
| 1 | Lockwood Drive | 30 | two | +0.197% | -0.030% | +0.979% |
| 1.3 | Ashley Avenue | 0 | two | +0.152% | -0.022% | +0.572% |
| 1.3 | Spring Street | 1 | two | +0.030% | -0.023% | +0.033% |
| 1.3 | Coming Street | 2 | two | +0.107% | -0.012% | +0.736% |
| 1.3 | Rutledge Avenue | 3 | two | -0.023% | -0.017% | +0.261% |
| 1.3 | Coming Street | 8 | two | +0.024% | -0.013% | +0.326% |
| 1.3 | King Street | 9 | fwd | -0.032% | -0.032% | -0.068% |
| 1.3 | Rutledge Avenue | 12 | two | +0.321% | -0.072% | +0.627% |
| 1.3 | Morrison Drive | 14 | two | +0.015% | +0.010% | +0.511% |
| 1.3 | Meeting Street | 25 | two | +0.012% | -0.011% | +0.501% |
| 1.3 | Lockwood Drive | 30 | two | +0.458% | -0.058% | +0.979% |
| 1.3 | Courtenay Drive | 39 | fwd | +0.261% | -0.040% | -0.332% |
| 1.6 | Spring Street | 1 | two | -0.048% | -0.009% | +0.033% |
| 1.6 | Coming Street | 2 | two | +0.138% | -0.026% | +0.736% |
| 1.6 | Rutledge Avenue | 3 | two | +0.007% | -0.036% | +0.261% |
| 1.6 | Coming Street | 8 | two | +0.015% | -0.009% | +0.326% |
| 1.6 | King Street | 9 | fwd | -0.072% | -0.027% | -0.068% |
| 1.6 | Rutledge Avenue | 10 | two | -0.004% | -0.008% | +0.159% |
| 1.6 | Rutledge Avenue | 12 | two | +0.362% | -0.046% | +0.627% |
| 1.6 | Morrison Drive | 14 | two | +0.026% | -0.003% | +0.511% |
| 1.6 | Meeting Street | 25 | two | -0.019% | +0.001% | +0.501% |
| 1.6 | Lockwood Drive | 30 | two | +0.709% | -0.091% | +0.979% |
| 1.6 | Coming Street | 38 | two | +0.002% | -0.010% | +0.194% |
| 1.6 | Courtenay Drive | 39 | fwd | +0.421% | -0.056% | -0.332% |

## 5. Why the city results moved since HANDOFF section 6 (bonus 1.1, demand x1.0)

Same layouts, same code, demand switched back one Task 2 change at a time. The first row of each block reproduces the earlier P5 numbers.

| config | demand_model | peak | mean | p10 | median | p90 | improved_share | verdict |
|---|---|---|---|---|---|---|---|---|
| Ashley Avenue | old: K .09, split .60, no non-work | am | -0.232% | -0.440% | -0.185% | -0.066% | 100% | detectable: better |
| Ashley Avenue | measured K and split, no non-work | am | -0.091% | -0.194% | -0.070% | -0.035% | 100% | not detectable |
| Ashley Avenue | final (Task 2): measured K and split + fitted non-work | am | -0.032% | -0.050% | -0.028% | -0.008% | 100% | not detectable |
| Ashley Avenue | final (Task 2): measured K and split + fitted non-work | pm | +0.204% | +0.114% | +0.178% | +0.322% | 0% | detectable: worse |
| Ashley Avenue | final (Task 2): measured K and split + fitted non-work | am+pm | +0.089% | +0.035% | +0.080% | +0.147% | 0% | not detectable |
| Ashley Calhoun-Crosstown | old: K .09, split .60, no non-work | am | -0.231% | -0.441% | -0.173% | -0.066% | 100% | detectable: better |
| Ashley Calhoun-Crosstown | measured K and split, no non-work | am | -0.091% | -0.194% | -0.070% | -0.035% | 100% | not detectable |
| Ashley Calhoun-Crosstown | final (Task 2): measured K and split + fitted non-work | am | -0.033% | -0.050% | -0.031% | -0.011% | 100% | not detectable |
| Ashley Calhoun-Crosstown | final (Task 2): measured K and split + fitted non-work | pm | +0.122% | +0.026% | +0.110% | +0.255% | 0% | detectable: worse |
| Ashley Calhoun-Crosstown | final (Task 2): measured K and split + fitted non-work | am+pm | +0.046% | -0.002% | +0.031% | +0.117% | 15% | not detectable |
| Coming Street | old: K .09, split .60, no non-work | am | -0.225% | -0.268% | -0.227% | -0.186% | 100% | detectable: better |
| Coming Street | measured K and split, no non-work | am | -0.180% | -0.212% | -0.183% | -0.140% | 100% | detectable: better |
| Coming Street | final (Task 2): measured K and split + fitted non-work | am | -0.167% | -0.207% | -0.169% | -0.138% | 100% | detectable: better |
| Coming Street | final (Task 2): measured K and split + fitted non-work | pm | -0.093% | -0.145% | -0.111% | -0.015% | 100% | not detectable |
| Coming Street | final (Task 2): measured K and split + fitted non-work | am+pm | -0.130% | -0.170% | -0.129% | -0.081% | 100% | detectable: better |
| Rutledge Avenue | old: K .09, split .60, no non-work | am | +0.469% | +0.203% | +0.393% | +0.944% | 0% | detectable: worse |
| Rutledge Avenue | measured K and split, no non-work | am | +0.201% | +0.028% | +0.176% | +0.435% | 5% | detectable: worse |
| Rutledge Avenue | final (Task 2): measured K and split + fitted non-work | am | +0.263% | +0.104% | +0.233% | +0.509% | 0% | detectable: worse |
| Rutledge Avenue | final (Task 2): measured K and split + fitted non-work | pm | +0.033% | -0.062% | +0.014% | +0.151% | 35% | not detectable |
| Rutledge Avenue | final (Task 2): measured K and split + fitted non-work | am+pm | +0.145% | +0.033% | +0.161% | +0.253% | 10% | detectable: worse |
| all three | old: K .09, split .60, no non-work | am | -0.235% | -0.291% | -0.230% | -0.182% | 100% | detectable: better |
| all three | measured K and split, no non-work | am | -0.199% | -0.259% | -0.189% | -0.140% | 100% | detectable: better |
| all three | final (Task 2): measured K and split + fitted non-work | am | -0.143% | -0.226% | -0.162% | -0.051% | 100% | detectable: better |
| all three | final (Task 2): measured K and split + fitted non-work | pm | -0.087% | -0.191% | -0.114% | +0.058% | 75% | not detectable |
| all three | final (Task 2): measured K and split + fitted non-work | am+pm | -0.114% | -0.189% | -0.125% | -0.016% | 90% | detectable: better |

## 6. Pareto moves confirmed on all scenarios (AM+PM)

| config | demand | mean | p10 | median | p90 | improved_share | vkm_mean | verdict |
|---|---|---|---|---|---|---|---|---|
| Ashley Avenue [0] two | 1 | +0.046% | -0.002% | +0.031% | +0.117% | 15% | -0.036% | not detectable |
| Coming Street [2] two | 1 | +0.078% | +0.036% | +0.065% | +0.151% | 0% | -0.007% | not detectable |
| Rutledge Avenue [3] two | 1 | -0.042% | -0.062% | -0.042% | -0.020% | 100% | -0.030% | not detectable |
| Coming Street [8] two | 1 | +0.003% | -0.006% | +0.003% | +0.011% | 25% | -0.014% | not detectable |
| King Street [9] fwd | 1 | -0.021% | -0.041% | -0.019% | -0.008% | 95% | -0.048% | not detectable |
| Rutledge Avenue [12] two | 1 | +0.197% | +0.091% | +0.204% | +0.314% | 0% | -0.051% | detectable: worse |
| Morrison Drive [14] two | 1 | +0.013% | +0.004% | +0.011% | +0.024% | 0% | -0.002% | not detectable |
| Meeting Street [25] two | 1 | +0.001% | -0.008% | +0.003% | +0.008% | 35% | -0.004% | not detectable |
| Lockwood Drive [30] two | 1 | +0.209% | +0.148% | +0.195% | +0.304% | 0% | -0.025% | detectable: worse |
| Spring Street [1] two | 1 | -0.013% | -0.031% | -0.014% | +0.008% | 75% | -0.012% | not detectable |
| Courtenay Drive [39] fwd | 1 | +0.049% | -0.003% | +0.030% | +0.148% | 10% | -0.004% | not detectable |
| Rutledge Avenue [10] two | 1 | -0.005% | -0.010% | -0.005% | -0.000% | 90% | -0.006% | not detectable |
| Coming Street [38] two | 1 | -0.009% | -0.015% | -0.010% | -0.001% | 95% | -0.010% | not detectable |
| Ashley Avenue [0] two | 1.3 | +0.112% | +0.027% | +0.114% | +0.193% | 0% | -0.025% | detectable: worse |
| Coming Street [2] two | 1.3 | +0.137% | +0.104% | +0.130% | +0.180% | 0% | -0.013% | detectable: worse |
| Rutledge Avenue [3] two | 1.3 | +0.005% | -0.026% | +0.009% | +0.028% | 35% | -0.029% | not detectable |
| Coming Street [8] two | 1.3 | +0.014% | -0.002% | +0.015% | +0.028% | 15% | -0.013% | not detectable |
| King Street [9] fwd | 1.3 | -0.030% | -0.058% | -0.026% | -0.004% | 90% | -0.032% | not detectable |
| Rutledge Avenue [12] two | 1.3 | +0.342% | +0.205% | +0.365% | +0.467% | 0% | -0.051% | detectable: worse |
| Morrison Drive [14] two | 1.3 | +0.033% | +0.015% | +0.032% | +0.050% | 0% | +0.004% | not detectable |
| Meeting Street [25] two | 1.3 | +0.002% | -0.006% | +0.002% | +0.008% | 30% | -0.006% | not detectable |
| Lockwood Drive [30] two | 1.3 | +0.422% | +0.324% | +0.394% | +0.520% | 0% | -0.045% | detectable: worse |
| Spring Street [1] two | 1.3 | -0.014% | -0.030% | -0.020% | +0.009% | 80% | -0.011% | not detectable |
| Courtenay Drive [39] fwd | 1.3 | +0.238% | +0.118% | +0.216% | +0.455% | 0% | -0.032% | detectable: worse |
| Rutledge Avenue [10] two | 1.3 | +0.000% | -0.007% | -0.001% | +0.008% | 55% | -0.005% | not detectable |
| Coming Street [38] two | 1.3 | -0.003% | -0.009% | -0.002% | +0.004% | 60% | -0.010% | not detectable |
| Ashley Avenue [0] two | 1.6 | +0.170% | +0.078% | +0.167% | +0.271% | 0% | -0.008% | detectable: worse |
| Coming Street [2] two | 1.6 | +0.181% | +0.119% | +0.176% | +0.241% | 0% | -0.026% | detectable: worse |
| Rutledge Avenue [3] two | 1.6 | +0.038% | +0.014% | +0.041% | +0.061% | 0% | -0.027% | not detectable |
| Coming Street [8] two | 1.6 | +0.033% | +0.020% | +0.029% | +0.053% | 0% | -0.014% | not detectable |
| King Street [9] fwd | 1.6 | -0.047% | -0.082% | -0.044% | -0.011% | 90% | -0.023% | not detectable |
| Rutledge Avenue [12] two | 1.6 | +0.460% | +0.279% | +0.493% | +0.601% | 0% | -0.028% | detectable: worse |
| Morrison Drive [14] two | 1.6 | +0.051% | +0.041% | +0.052% | +0.060% | 0% | +0.004% | not detectable |
| Meeting Street [25] two | 1.6 | +0.006% | -0.002% | +0.007% | +0.015% | 15% | -0.003% | not detectable |
| Lockwood Drive [30] two | 1.6 | +0.691% | +0.535% | +0.646% | +0.896% | 0% | -0.069% | detectable: worse |
| Spring Street [1] two | 1.6 | -0.020% | -0.035% | -0.022% | -0.003% | 95% | -0.005% | not detectable |
| Courtenay Drive [39] fwd | 1.6 | +0.433% | +0.305% | +0.427% | +0.579% | 0% | -0.027% | detectable: worse |
| Rutledge Avenue [10] two | 1.6 | +0.000% | -0.007% | -0.000% | +0.006% | 50% | -0.004% | not detectable |
| Coming Street [38] two | 1.6 | +0.005% | -0.002% | +0.006% | +0.012% | 15% | -0.006% | not detectable |
