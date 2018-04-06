from django.shortcuts import render,HttpResponse

# Create your views here.
import json,time
from django.views.generic.base import View
from django.utils.safestring import mark_safe

from search.models import ArticleType
from elasticsearch import Elasticsearch
from pure_pagination import Paginator, EmptyPage, PageNotAnInteger
from redis import StrictRedis

client = Elasticsearch(hosts=['localhost'])  # 另一种建立连接的方式，更底层，最原始的方式
redis_cli = StrictRedis()


class IndexView(View):
    def get(self,request):
        topn_search = redis_cli.zrevrangebyscore("hot_search","+inf","-inf",start=0,num=5)
        return render(request,'index.html',{"topn_search":topn_search})


class SuggestView(View):
    def get(self,request):
        key_words = request.GET.get('s','')
        re_data = []
        if key_words:
            # elasticsearch suggest接口
            s = ArticleType.search()
            s = s.suggest('my-suggest',key_words,completion={
                "field":"suggest",
                "fuzzy":{
                    "fuzziness":3
                },
                "size":15
            })
            suggestions = s.execute_suggest() # 执行搜索
            for match in getattr(suggestions,"my-suggest")[0].options:
                source = match._source
                re_data.append(source['title'])# 获取搜索title的结果
                return HttpResponse(json.dumps(re_data),content_type='application/json')


class SearchView(View):
    def get(self,request):
        key_words = request.GET.get('q','')
        s_type = request.GET.get('s_type','article')
        redis_cli.zincrby("hot_search",key_words)
        topn_search = redis_cli.zrevrangebyscore("hot_search","+inf","-inf",start=0,num=5)

        try:
            page = request.GET.get('page', 1)
        except PageNotAnInteger:
            page = 1

        start_time = time.time()
        allNums = client.count(index='jobbole')['count']
        response = client.search(
            index="jobbole",
            body={
                  "query": {
                    "multi_match": {
                      "query": key_words,
                      "fields": ["title","content"]
                    }
                  },
                  "from": 0,
                  "size": 20,
                  "highlight": {
                    "pre_tags": ["<span class='keyWord'>"],
                    "post_tags": ["</span>"],
                    "fields": {
                      "title":{},
                      "content":{}
                    }
                  }
                }
        )
        end_time = time.time()
        hit_list = []
        for hit in response['hits']['hits']:
            hit_dict = {}
            if 'title' in hit['highlight']:
                hit_dict['title'] = ''.join(hit['highlight']['title'])
            else:
                hit_dict['title'] = hit['_source']['title']
            if 'content' in hit['highlight']:
                hit_dict['content'] = ''.join(hit['highlight']['content'][:500])
            else:
                hit_dict['content'] = hit['_source']['content']

            hit_dict['create_date'] = hit['_source']['create_date']
            hit_dict['url'] = hit['_source']['url']
            hit_dict['score'] = hit['_score']

            hit_list.append(hit_dict)

        total_nums = len(hit_list)

        per_page = 5
        p = Paginator(hit_list,per_page=per_page,request=request)
        hit_list_data = p.page(page)
        start_page = int(page)*per_page-1*per_page
        end_page = int(page)*per_page
        spend_time = round(end_time - start_time,7)
        return render(request,'result.html',{'topn_search':topn_search,'allNums':allNums,'spend_time':spend_time,'hit_list_data':hit_list_data,'page':page,'total_nums':total_nums,'key_words':key_words,'s_type':s_type,"start_page":start_page,'end_page':end_page})




