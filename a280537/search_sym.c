/* No-four-in-plane (OEIS A280537) search with 3-fold rotational symmetry.
 *
 * Same min-conflicts tabu search as search5.c, but points are added and
 * removed in orbits of the rotation (x,y,z) -> (y,z,x): 3-point orbits plus
 * up to 2 points on the diagonal x=y=z (a third would be collinear).
 *   cnt[c] = number of point triples whose plane passes through cell c
 *   lin[c] = number of point pairs whose line passes through cell c
 * Total conflict 0 = valid configuration of 3*orbits + diag points.
 *
 * Usage: ./search_sym N orbits diag seed seconds [out.json]
 *   e.g. ./search_sym 28 19 2 1 3600 out.json   (59 points)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define MAXN 40
#define MAXK 128
static int N, NC;
static int *cnt, *lin, *tabu, *inS;
static int S[MAXK][3], k = 0;
static long long iter = 0;

static inline int idx(int x, int y, int z) { return (x * N + y) * N + z; }
static int gcd(int a, int b) { if (a < 0) a = -a; if (b < 0) b = -b; while (b) { int t = a % b; a = b; b = t; } return a; }

static unsigned long long rs;
static inline unsigned rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (unsigned)(rs >> 11); }

/* p,a,b 평면 위 모든 격자점에 d 더하기 */
static void plane_add(const int *p, const int *a, const int *b, int d) {
    int u[3] = {a[0]-p[0], a[1]-p[1], a[2]-p[2]};
    int v[3] = {b[0]-p[0], b[1]-p[1], b[2]-p[2]};
    int n[3] = {u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]};
    int g = gcd(gcd(n[0], n[1]), n[2]);
    if (g == 0) return;
    n[0] /= g; n[1] /= g; n[2] /= g;
    int D = n[0]*p[0] + n[1]*p[1] + n[2]*p[2];
    int s = 0, an = abs(n[0]);
    if (abs(n[1]) > an) { s = 1; an = abs(n[1]); }
    if (abs(n[2]) > an) { s = 2; }
    int i1 = (s + 1) % 3, i2 = (s + 2) % 3, c[3];
    for (c[i1] = 0; c[i1] < N; c[i1]++) {
        int r0 = D - n[i1]*c[i1];
        for (c[i2] = 0; c[i2] < N; c[i2]++) {
            int r = r0 - n[i2]*c[i2];
            if (r % n[s]) continue;
            int t = r / n[s];
            if (t < 0 || t >= N) continue;
            c[s] = t;
            cnt[idx(c[0], c[1], c[2])] += d;
        }
    }
}

static void line_add(const int *a, const int *b, int d) {
    int dir[3] = {b[0]-a[0], b[1]-a[1], b[2]-a[2]};
    int g = gcd(gcd(dir[0], dir[1]), dir[2]);
    dir[0] /= g; dir[1] /= g; dir[2] /= g;
    int c[3] = {a[0], a[1], a[2]};
    while (c[0]-dir[0] >= 0 && c[0]-dir[0] < N && c[1]-dir[1] >= 0 && c[1]-dir[1] < N &&
           c[2]-dir[2] >= 0 && c[2]-dir[2] < N) { c[0] -= dir[0]; c[1] -= dir[1]; c[2] -= dir[2]; }
    while (c[0] >= 0 && c[0] < N && c[1] >= 0 && c[1] < N && c[2] >= 0 && c[2] < N) {
        lin[idx(c[0], c[1], c[2])] += d;
        c[0] += dir[0]; c[1] += dir[1]; c[2] += dir[2];
    }
}

static void add_point(int ci) {
    int p[3] = {ci / (N*N), (ci / N) % N, ci % N};
    for (int i = 0; i < k; i++) {
        line_add(p, S[i], 1);
        for (int j = i + 1; j < k; j++) plane_add(p, S[i], S[j], 1);
    }
    memcpy(S[k], p, sizeof p); k++; inS[ci] = 1;
}

static void remove_point(int pos) {
    int p[3]; memcpy(p, S[pos], sizeof p);
    inS[idx(p[0], p[1], p[2])] = 0;
    memcpy(S[pos], S[k-1], sizeof p); k--;
    for (int i = 0; i < k; i++) {
        line_add(p, S[i], -1);
        for (int j = i + 1; j < k; j++) plane_add(p, S[i], S[j], -1);
    }
}

static inline long long base(void) { return (long long)(k-1)*(k-2)/2; }

static long long total_conflict(void) {
    long long e = 0, b = base();
    for (int i = 0; i < k; i++) e += cnt[idx(S[i][0], S[i][1], S[i][2])] - b;
    return e / 4;
}

/* 넣을 칸: 직선 위반 없음, 타부 아님, cnt 최소 (동점은 무작위) */
static int best_cell(void) {
    int best = -1, bv = 1 << 30, ties = 0;
    for (int c = 0; c < NC; c++) {
        if (inS[c] || lin[c] || tabu[c] > iter) continue;
        int v = cnt[c];
        if (v < bv) { bv = v; best = c; ties = 1; }
        else if (v == bv && rnd() % (++ties) == 0) best = c;
    }
    return best;
}

/* 뺄 점: 충돌 가장 큰 점 (가끔 충돌 있는 점 중 무작위) */
static int worst_point(void) {
    long long b = base();
    int best = -1, ties = 0; long long bv = -1;
    if (rnd() % 10 == 0) {
        int cand[MAXK], m = 0;
        for (int i = 0; i < k; i++) if (cnt[idx(S[i][0], S[i][1], S[i][2])] - b > 0) cand[m++] = i;
        if (m) return cand[rnd() % m];
    }
    for (int i = 0; i < k; i++) {
        long long v = cnt[idx(S[i][0], S[i][1], S[i][2])] - b;
        if (v > bv) { bv = v; best = i; ties = 1; }
        else if (v == bv && rnd() % (++ties) == 0) best = i;
    }
    return best;
}

static void save(const char *path) {
    FILE *f = fopen(path, "w");
    fprintf(f, "[");
    for (int i = 0; i < k; i++) fprintf(f, "%s[%d,%d,%d]", i ? "," : "", S[i][0], S[i][1], S[i][2]);
    fprintf(f, "]\n");
    fclose(f);
}


/* 대칭: (x,y,z) -> (y,z,x) 순환 (대각선 축 120도 회전) */
static int orbit(int c, int *o) {
    int x = c / (N*N), y = (c / N) % N, z = c % N;
    o[0] = c; int m = 1;
    int b = idx(y, z, x), d = idx(z, x, y);
    if (b != c) o[m++] = b;
    if (d != c && d != b) o[m++] = d;
    return m;
}
static int find_pos(int c) { for (int i = 0; i < k; i++) if (idx(S[i][0],S[i][1],S[i][2]) == c) return i; return -1; }

static int add_orbit(int c) {           /* 성공하면 1, 직선 위반이면 되돌리고 0 */
    int o[3], m = orbit(c, o), added = 0;
    for (int i = 0; i < m; i++) {
        if (inS[o[i]] || lin[o[i]]) { for (int j = 0; j < added; j++) remove_point(find_pos(o[j])); return 0; }
        add_point(o[i]); added++;
    }
    return 1;
}
static void remove_orbit(int c) { int o[3], m = orbit(c, o); for (int i = 0; i < m; i++) { int p = find_pos(o[i]); if (p >= 0) remove_point(p); } }

static int orbit_score(int c) { int o[3], m = orbit(c, o), s = 0; for (int i = 0; i < m; i++) { if (inS[o[i]] || lin[o[i]]) return 1 << 29; s += cnt[o[i]]; } return s; }

static int best_orbit(int want_size, int ndiag_allowed) {
    int best = -1, bv = 1 << 28, ties = 0, o[3];
    for (int c = 0; c < NC; c++) {
        int x = c / (N*N), y = (c / N) % N, z = c % N;
        if (!(x <= y && x <= z)) continue;            /* 궤도 대표만 */
        if (tabu[c] > iter) continue;
        int m = orbit(c, o);
        if (m == 1 && !ndiag_allowed) continue;
        if (want_size && m != want_size) continue;
        int v = orbit_score(c);
        if (v < bv) { bv = v; best = c; ties = 1; }
        else if (v == bv && rnd() % (++ties) == 0) best = c;
    }
    return best;
}
static int count_diag(void) { int d = 0; for (int i = 0; i < k; i++) if (S[i][0]==S[i][1] && S[i][1]==S[i][2]) d++; return d; }
static int rep(int c) { int o[3], m = orbit(c, o), r = c; for (int i = 0; i < m; i++) if (o[i] < r) r = o[i]; return r; }

int main(int argc, char **argv) {
    if (argc < 6) { fprintf(stderr, "usage: N orbits3 diag seed seconds [out]\n"); return 1; }
    N = atoi(argv[1]); int norb = atoi(argv[2]), ndiag = atoi(argv[3]);
    rs = 88172645463325252ULL ^ (unsigned long long)atoll(argv[4]) * 2654435761ULL;
    double limit = atof(argv[5]);
    char out[256]; snprintf(out, sizeof out, "%s", argc > 6 ? argv[6] : "sym.json");
    NC = N * N * N;
    cnt = calloc(NC, sizeof *cnt); lin = calloc(NC, sizeof *lin);
    tabu = calloc(NC, sizeof *tabu); inS = calloc(NC, sizeof *inS);
    for (int i = 0; i < 20; i++) rnd();
    int target = 3 * norb + ndiag;

    /* 대각선 점 먼저 */
    while (count_diag() < ndiag) { int c = best_orbit(1, 1); if (c < 0 || !add_orbit(c)) { tabu[c] = 1<<30; } }
    while (k < target) { int c = best_orbit(3, 0); if (c < 0) break; if (!add_orbit(c)) tabu[c] = iter + 1000000; }
    for (int c = 0; c < NC; c++) tabu[c] = 0;
    printf("start k=%d target=%d conflicts=%lld\n", k, target, total_conflict()); fflush(stdout);

    clock_t t0 = clock();
    long long e = total_conflict(), beste = e;
    int tenure = 5 + N / 2;
    while ((double)(clock() - t0) / CLOCKS_PER_SEC < limit) {
        iter++;
        int pos = worst_point();
        int pc = idx(S[pos][0], S[pos][1], S[pos][2]);
        int o[3], m = orbit(pc, o);
        remove_orbit(pc);
        tabu[rep(pc)] = iter + tenure + rnd() % tenure;
        int c = best_orbit(m, m == 1);
        if (c < 0 || !add_orbit(c)) { add_orbit(rep(pc)); continue; }
        e = total_conflict();
        if (e < beste) {
            beste = e;
            printf("iter %lld  best_conflicts=%lld  %.0fs\n", iter, beste, (double)(clock()-t0)/CLOCKS_PER_SEC); fflush(stdout);
        }
        if (e == 0) { save(out); printf("FOUND %d\n", k); fflush(stdout); return 0; }
    }
    printf("END k=%d best_conflicts=%lld\n", k, beste);
    return 0;
}
