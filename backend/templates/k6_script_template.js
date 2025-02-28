import http from 'k6/http';
import { check, sleep } from 'k6';
import { htmlReport } from '../k6_reporter.js';

export let options = {
    vus: __VUS__,
    duration: '__DURATION__s',
    thresholds: {
        http_req_duration: ['p(95)<2000'], // 95% 的请求响应时间小于 2 秒
        http_req_failed: ['rate<0.1'],      // 错误率小于 10%
    },
};

export default function() {
    // 在这里添加测试场景
    const response = http.get('http://test.k6.io');
    
    check(response, {
        'is status 200': (r) => r.status === 200,
    });
    
    sleep(1);
}

export function handleSummary(data) {
    return {
        'report.html': htmlReport(data),
        'stdout': JSON.stringify(data, null, 2),
    };
} 